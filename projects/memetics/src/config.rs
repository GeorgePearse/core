//! Validate standing authorizations before storing or executing them.

use crate::error::{Result, invalid};
use regex::Regex;
use serde_json::{Map, Value};
use sha2::{Digest, Sha256};
use std::sync::LazyLock;

static ID: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"^[a-zA-Z0-9_-]{1,80}$").unwrap());
static REPO: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$").unwrap());
static REF: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"^[A-Za-z0-9_][A-Za-z0-9_./-]*$").unwrap());
static SHA: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"^[a-f0-9]{40}$").unwrap());
static IMAGE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"^[A-Za-z0-9][A-Za-z0-9_./:@-]*$").unwrap());

fn sorted(value: &Value) -> Value {
    match value {
        Value::Object(map) => {
            let mut keys: Vec<&String> = map.keys().collect();
            keys.sort();
            Value::Object(
                keys.into_iter()
                    .map(|k| (k.clone(), sorted(&map[k])))
                    .collect(),
            )
        }
        Value::Array(items) => Value::Array(items.iter().map(sorted).collect()),
        other => other.clone(),
    }
}

/// Compact, key-sorted, ASCII-escaped JSON, byte-identical to Python's
/// `json.dumps(sort_keys=True, separators=(",", ":"))` so digests survive the port.
pub fn canonical(value: &Value) -> String {
    let text = serde_json::to_string(&sorted(value)).expect("JSON values serialize");
    let mut out = String::with_capacity(text.len());
    for c in text.chars() {
        if c.is_ascii() {
            out.push(c);
        } else {
            let mut units = [0u16; 2];
            for unit in c.encode_utf16(&mut units) {
                out.push_str(&format!("\\u{unit:04x}"));
            }
        }
    }
    out
}

pub fn digest(value: &Value) -> String {
    hex::encode(Sha256::digest(canonical(value).as_bytes()))
}

pub fn repo_name(value: &Value) -> Result<String> {
    let name = value
        .as_str()
        .filter(|v| REPO.is_match(v))
        .ok_or_else(|| invalid("repository must be owner/name"))?;
    if name.split('/').any(|p| p == "." || p == "..") {
        return Err(invalid("invalid repository"));
    }
    Ok(name.to_string())
}

pub fn safe_path(value: &str) -> Result<&str> {
    if value.is_empty() || value.contains('\\') || value.contains('\0') {
        return Err(invalid("invalid relative path"));
    }
    let parts: Vec<&str> = value
        .split('/')
        .filter(|p| !p.is_empty() && *p != ".")
        .collect();
    if value.starts_with('/')
        || parts.is_empty()
        || parts.iter().any(|p| *p == ".." || *p == ".git")
    {
        return Err(invalid(
            "path must remain inside the checkout and outside .git",
        ));
    }
    Ok(value)
}

/// Destination write boundary: a trailing `/` authorizes a directory recursively,
/// anything else authorizes exactly one file.
pub fn in_scope(path: &str, scopes: &[String]) -> bool {
    scopes.iter().any(|scope| {
        path == scope.trim_end_matches('/')
            || (scope.ends_with('/') && path.starts_with(scope.as_str()))
    })
}

pub fn strings(value: Option<&Value>) -> Vec<String> {
    value
        .and_then(Value::as_array)
        .map(|items| {
            items
                .iter()
                .filter_map(|v| v.as_str().map(String::from))
                .collect()
        })
        .unwrap_or_default()
}

/// Destination paths plus test paths: everything the model may write.
pub fn write_scopes(config: &Value) -> Vec<String> {
    let destination = &config["destination"];
    let mut scopes = strings(destination.get("paths"));
    scopes.extend(strings(destination.get("test_paths")));
    scopes
}

pub fn truthy(value: Option<&Value>) -> bool {
    match value {
        None | Some(Value::Null) => false,
        Some(Value::Bool(b)) => *b,
        Some(Value::Number(n)) => n.as_f64() != Some(0.0),
        Some(Value::String(s)) => !s.is_empty(),
        Some(Value::Array(a)) => !a.is_empty(),
        Some(Value::Object(o)) => !o.is_empty(),
    }
}

fn object<'a>(map: &'a mut Map<String, Value>, key: &str) -> Result<&'a mut Map<String, Value>> {
    map.get_mut(key)
        .and_then(Value::as_object_mut)
        .ok_or_else(|| invalid(format!("{key} is required")))
}

pub fn validate(config: &Value) -> Result<Value> {
    let mut c = sorted(config);
    let root = c
        .as_object_mut()
        .ok_or_else(|| invalid("listener must be an object"))?;
    if !root
        .get("id")
        .and_then(Value::as_str)
        .is_some_and(|id| ID.is_match(id))
    {
        return Err(invalid(
            "listener id must contain 1-80 letters, numbers, underscores or hyphens",
        ));
    }
    match root.get("enabled") {
        None => {
            root.insert("enabled".into(), Value::Bool(true));
        }
        Some(Value::Bool(_)) => {}
        Some(_) => return Err(invalid("enabled must be boolean")),
    }
    if !root
        .get("concern")
        .and_then(Value::as_str)
        .is_some_and(|c| !c.trim().is_empty())
    {
        return Err(invalid("concern is required"));
    }
    for (section, ref_key) in [("upstream", "ref"), ("destination", "base_ref")] {
        let value = object(root, section)?;
        let repo = repo_name(value.get("repository").unwrap_or(&Value::Null))?.to_lowercase();
        value.insert("repository".into(), Value::String(repo));
        let ok = value.get(ref_key).and_then(Value::as_str).is_some_and(|r| {
            REF.is_match(r)
                && !r.contains("..")
                && !r.contains("//")
                && !r.ends_with('/')
                && !r.ends_with(".lock")
                && !r.ends_with('.')
        });
        if !ok {
            return Err(invalid("invalid tracked branch"));
        }
        let paths = match value.get("paths") {
            Some(Value::Array(p)) if !p.is_empty() => p.clone(),
            _ => return Err(invalid(format!("{section}.paths is required"))),
        };
        let tests = match value.get("test_paths") {
            None => vec![],
            Some(Value::Array(t)) => t.clone(),
            Some(_) => return Err(invalid(format!("{section}.test_paths must be a list"))),
        };
        for path in paths.iter().chain(tests.iter()) {
            safe_path(
                path.as_str()
                    .ok_or_else(|| invalid("invalid relative path"))?,
            )?;
        }
    }
    if !root["upstream"]
        .get("baseline_commit")
        .and_then(Value::as_str)
        .is_some_and(|s| SHA.is_match(s))
    {
        return Err(invalid(
            "upstream.baseline_commit must be an immutable 40-character SHA",
        ));
    }
    let adaptation = object(root, "adaptation")?;
    if !adaptation.get("instructions").is_some_and(Value::is_string) {
        return Err(invalid("adaptation.instructions is required"));
    }
    let commands_ok = match adaptation.get("validation_commands") {
        Some(Value::Array(commands)) => {
            (1..=10).contains(&commands.len())
                && commands
                    .iter()
                    .all(|x| x.as_str().is_some_and(|s| !s.trim().is_empty()))
        }
        _ => false,
    };
    if !commands_ok {
        return Err(invalid("at least one validation command is required"));
    }
    let image = adaptation
        .entry("validation_image")
        .or_insert_with(|| Value::String("python:3.13-slim".into()));
    if !image.as_str().is_some_and(|i| IMAGE.is_match(i)) {
        return Err(invalid("invalid validation image"));
    }
    let timeout = adaptation
        .entry("timeout_seconds")
        .or_insert_with(|| Value::from(120));
    if !timeout.as_i64().is_some_and(|t| (1..=900).contains(&t)) {
        return Err(invalid("validation timeout must be 1-900 seconds"));
    }
    let delivery = root
        .entry("delivery")
        .or_insert_with(|| Value::Object(Map::new()))
        .as_object_mut()
        .ok_or_else(|| invalid("delivery must be an object"))?;
    if truthy(delivery.get("auto_merge"))
        || delivery
            .get("mode")
            .map(|m| m.as_str() != Some("automatic_draft_pr"))
            .unwrap_or(false)
    {
        return Err(invalid(
            "only automatic draft PR delivery is supported; auto-merge is forbidden",
        ));
    }
    if delivery
        .get("update_existing_pr")
        .is_some_and(|v| v != &Value::Bool(true))
    {
        return Err(invalid("update_existing_pr must be true"));
    }
    delivery.insert("mode".into(), "automatic_draft_pr".into());
    delivery.insert("auto_merge".into(), false.into());
    delivery.insert("update_existing_pr".into(), true.into());
    Ok(sorted(&c))
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn canonical_and_digest_match_python() {
        assert_eq!(
            digest(&json!(["owner/repo", "main"])),
            "240046aad2334e358f3923206463cba3314ee0875bbb4df614e6aa5d1a5bf9a3"
        );
        let value = json!({"b": [1, "é\u{2026}😀\n\u{1}"], "a": null, "c": true});
        assert_eq!(
            canonical(&value),
            r#"{"a":null,"b":[1,"\u00e9\u2026\ud83d\ude00\n\u0001"],"c":true}"#
        );
        assert_eq!(
            digest(&value),
            "d67672bda8b955962861bc4fbe0d8589699e5376d2168236ebbfd128c02473fb"
        );
        assert_eq!(
            digest(&json!("owner/repo")),
            "1364542ad91c24a7367dc65c52d635b7269b4ce3a6a3db30e8c399eb4ee7c140"
        );
    }

    #[test]
    fn write_boundary_directory_vs_file() {
        let scopes = vec!["src/agent/".to_string(), "tests/one.ts".to_string()];
        assert!(in_scope("src/agent/deep/x.ts", &scopes));
        assert!(in_scope("src/agent", &scopes));
        assert!(in_scope("tests/one.ts", &scopes));
        assert!(!in_scope("tests/one.ts.bak", &scopes));
        assert!(!in_scope("tests/one.ts/x", &scopes));
        assert!(!in_scope("src/agentx/y.ts", &scopes));
    }

    #[test]
    fn unsafe_paths_rejected() {
        for bad in [
            "",
            "/etc/passwd",
            "../x",
            "a/../../b",
            ".git/config",
            "a\\b",
            ".",
            "./",
        ] {
            assert!(safe_path(bad).is_err(), "{bad}");
        }
        assert!(safe_path("src/./a.rs").is_ok());
    }
}
