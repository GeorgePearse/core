//! `memetics.md`: a committed, human-readable manifest of the ideas a repository implements.
//!
//! ```markdown
//! ## shared-watch
//! - idea: One upstream poll and blob index per repository and ref, shared by every listener.
//! - source: code swh:1:rev:<sha>;path=src/x.ts repo=https://github.com/o/r symbol=Pruner.prune hash=<b3>
//! - source: paper doi:10.1145/3597503 section=3.2
//! - source: article https://example.com/post
//! - code: src/engine.rs symbol=Engine::poll hash=<b3> lines=120-188
//! ```
//!
//! Anything before the first `## ` is free prose. Inside a section only the fixed bullets above
//! (and blank lines) are allowed, so `render(parse(text)) == text` for a well-formed file.

use crate::anchors::{self, Resolution};
use crate::error::{Result, invalid};
use regex::Regex;
use serde::Serialize;
use std::str::FromStr;
use std::sync::LazyLock;

pub const MANIFEST: &str = "memetics.md";

static IDEA_ID: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"^[a-z0-9][a-z0-9_-]{0,79}$").unwrap());
static HASH: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"^[0-9a-f]{16}$").unwrap());
static DOI: LazyLock<Regex> = LazyLock::new(|| Regex::new(r#"10\.\d{4,9}/[^\s"'<>,;]+"#).unwrap());
static ARXIV: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"(?i)arxiv(?:\.org/(?:abs|pdf)/|:\s*)(\d{4}\.\d{4,5}(?:v\d+)?)").unwrap()
});

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct Anchor {
    pub path: String,
    pub symbol: Option<String>,
    pub hash: Option<String>,
    pub lines: Option<(usize, usize)>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
#[serde(tag = "kind", rename_all = "lowercase")]
pub enum Source {
    /// Upstream code: a SWHID (`swh:1:rev:…;path=…;lines=…` as a citation hint) plus an anchor.
    Code {
        swhid: String,
        repo: Option<String>,
        symbol: Option<String>,
        hash: Option<String>,
    },
    /// `doi:10.…` or `arXiv:2510.22396`.
    Paper {
        id: String,
        section: Option<String>,
    },
    Article {
        url: String,
    },
}

impl Source {
    pub fn path(&self) -> Option<String> {
        let Source::Code { swhid, .. } = self else {
            return None;
        };
        swhid
            .split(';')
            .find_map(|q| q.strip_prefix("path="))
            .map(|p| p.trim_start_matches('/').to_string())
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct Idea {
    pub id: String,
    pub statement: String,
    pub sources: Vec<Source>,
    pub code: Vec<Anchor>,
}

#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub struct Manifest {
    pub preamble: String,
    pub ideas: Vec<Idea>,
}

fn tokens(text: &str) -> Result<Vec<String>> {
    let mut out = Vec::new();
    let mut current = String::new();
    let mut quoted = false;
    for c in text.chars() {
        match c {
            '"' => quoted = !quoted,
            c if c.is_whitespace() && !quoted => {
                if !current.is_empty() {
                    out.push(std::mem::take(&mut current));
                }
            }
            c => current.push(c),
        }
    }
    if quoted {
        return Err(invalid("unterminated quote"));
    }
    if !current.is_empty() {
        out.push(current);
    }
    Ok(out)
}

fn quote(value: &str) -> String {
    if value.chars().any(char::is_whitespace) {
        format!("\"{value}\"")
    } else {
        value.to_string()
    }
}

fn fields(items: &[String], allowed: &[&str]) -> Result<Vec<(String, String)>> {
    items
        .iter()
        .map(|item| {
            let (k, v) = item
                .split_once('=')
                .ok_or_else(|| invalid(format!("expected key=value, got {item}")))?;
            if !allowed.contains(&k) {
                return Err(invalid(format!("unknown field {k}")));
            }
            Ok((k.to_string(), v.to_string()))
        })
        .collect()
}

fn get(fields: &[(String, String)], key: &str) -> Option<String> {
    fields
        .iter()
        .find(|(k, _)| k == key)
        .map(|(_, v)| v.clone())
}

fn hash_field(fields: &[(String, String)]) -> Result<Option<String>> {
    match get(fields, "hash") {
        Some(h) if !HASH.is_match(&h) => Err(invalid("hash must be 16 lowercase hex characters")),
        h => Ok(h),
    }
}

pub fn parse_lines(value: &str) -> Result<(usize, usize)> {
    let (a, b) = value.split_once('-').unwrap_or((value, value));
    let parsed = (a.parse::<usize>(), b.parse::<usize>());
    match parsed {
        (Ok(a), Ok(b)) if a >= 1 && a <= b => Ok((a, b)),
        _ => Err(invalid(format!("invalid line range {value}"))),
    }
}

fn parse_anchor(value: &str) -> Result<Anchor> {
    let items = tokens(value)?;
    let (path, rest) = items
        .split_first()
        .ok_or_else(|| invalid("code needs a path"))?;
    crate::config::safe_path(path)?;
    let f = fields(rest, &["symbol", "hash", "lines"])?;
    Ok(Anchor {
        path: path.clone(),
        symbol: get(&f, "symbol"),
        hash: hash_field(&f)?,
        lines: get(&f, "lines").map(|l| parse_lines(&l)).transpose()?,
    })
}

pub fn paper_id(value: &str) -> Option<String> {
    let lower = value.to_ascii_lowercase();
    if lower.starts_with("doi:") && DOI.is_match(value) {
        return DOI.find(value).map(|m| format!("doi:{}", m.as_str()));
    }
    ARXIV.captures(value).map(|c| format!("arXiv:{}", &c[1]))
}

fn parse_source(value: &str) -> Result<Source> {
    let items = tokens(value)?;
    match items.as_slice() {
        [kind, id, rest @ ..] if kind == "code" => {
            swhid::QualifiedSwhid::from_str(id)
                .map_err(|e| invalid(format!("invalid SWHID {id}: {e}")))?;
            let f = fields(rest, &["repo", "symbol", "hash"])?;
            Ok(Source::Code {
                swhid: id.clone(),
                repo: get(&f, "repo"),
                symbol: get(&f, "symbol"),
                hash: hash_field(&f)?,
            })
        }
        [kind, id, rest @ ..] if kind == "paper" => {
            let normalised = paper_id(id)
                .ok_or_else(|| invalid(format!("paper needs doi:… or arXiv:…, got {id}")))?;
            if &normalised != id {
                return Err(invalid(format!("write the paper id as {normalised}")));
            }
            let f = fields(rest, &["section"])?;
            Ok(Source::Paper {
                id: id.clone(),
                section: get(&f, "section"),
            })
        }
        [kind, url] if kind == "article" && url.starts_with("http") => {
            Ok(Source::Article { url: url.clone() })
        }
        _ => Err(invalid(
            "source must be `code <swhid> …`, `paper <doi:|arXiv:> …` or `article <url>`",
        )),
    }
}

impl Manifest {
    pub fn parse(text: &str) -> Result<Manifest> {
        let mut manifest = Manifest::default();
        let mut preamble = Vec::new();
        let mut current: Option<Idea> = None;
        for (number, line) in text.lines().enumerate() {
            let fail = |e: crate::error::Error| invalid(format!("{MANIFEST}:{}: {e}", number + 1));
            if let Some(id) = line.strip_prefix("## ") {
                if let Some(idea) = current.take() {
                    manifest.push(idea).map_err(fail)?;
                }
                let id = id.trim();
                if !IDEA_ID.is_match(id) {
                    return Err(fail(invalid(
                        "idea id must be lowercase letters, digits, - or _",
                    )));
                }
                current = Some(Idea {
                    id: id.into(),
                    statement: String::new(),
                    sources: vec![],
                    code: vec![],
                });
                continue;
            }
            let Some(idea) = current.as_mut() else {
                preamble.push(line);
                continue;
            };
            if line.trim().is_empty() {
                continue;
            }
            let (key, value) = line
                .strip_prefix("- ")
                .and_then(|l| l.split_once(": "))
                .ok_or_else(|| fail(invalid("expected `- idea:`, `- source:` or `- code:`")))?;
            match key {
                "idea" if idea.statement.is_empty() => idea.statement = value.trim().to_string(),
                "idea" => return Err(fail(invalid("an idea has exactly one statement"))),
                "source" => idea.sources.push(parse_source(value).map_err(fail)?),
                "code" => idea.code.push(parse_anchor(value).map_err(fail)?),
                other => return Err(fail(invalid(format!("unknown key {other}")))),
            }
        }
        if let Some(idea) = current.take() {
            manifest
                .push(idea)
                .map_err(|e| invalid(format!("{MANIFEST}: {e}")))?;
        }
        manifest.preamble = preamble.join("\n").trim_end().to_string();
        Ok(manifest)
    }

    fn push(&mut self, idea: Idea) -> Result<()> {
        if idea.statement.is_empty() {
            return Err(invalid(format!("idea {} needs `- idea:`", idea.id)));
        }
        if idea.code.is_empty() {
            return Err(invalid(format!(
                "idea {} needs at least one `- code:` anchor",
                idea.id
            )));
        }
        if self.ideas.iter().any(|i| i.id == idea.id) {
            return Err(invalid(format!("duplicate idea {}", idea.id)));
        }
        self.ideas.push(idea);
        Ok(())
    }

    pub fn render(&self) -> String {
        let mut out = String::new();
        if !self.preamble.is_empty() {
            out.push_str(&self.preamble);
            out.push_str("\n\n");
        }
        let sections: Vec<String> = self.ideas.iter().map(Idea::render).collect();
        out.push_str(&sections.join("\n\n"));
        out.push('\n');
        out
    }

    pub fn idea(&self, id: &str) -> Option<&Idea> {
        self.ideas.iter().find(|i| i.id == id)
    }
}

impl Anchor {
    pub fn render(&self) -> String {
        let mut parts = vec![quote(&self.path)];
        if let Some(s) = &self.symbol {
            parts.push(format!("symbol={}", quote(s)));
        }
        if let Some(h) = &self.hash {
            parts.push(format!("hash={h}"));
        }
        if let Some((a, b)) = self.lines {
            parts.push(format!("lines={a}-{b}"));
        }
        parts.join(" ")
    }

    pub fn label(&self) -> String {
        match &self.symbol {
            Some(s) => format!("{} {s}", self.path),
            None => self.path.clone(),
        }
    }
}

impl Source {
    pub fn render(&self) -> String {
        match self {
            Source::Code {
                swhid,
                repo,
                symbol,
                hash,
            } => {
                let mut parts = vec!["code".to_string(), swhid.clone()];
                parts.extend(repo.iter().map(|r| format!("repo={r}")));
                parts.extend(symbol.iter().map(|s| format!("symbol={}", quote(s))));
                parts.extend(hash.iter().map(|h| format!("hash={h}")));
                parts.join(" ")
            }
            Source::Paper { id, section } => match section {
                Some(s) => format!("paper {id} section={}", quote(s)),
                None => format!("paper {id}"),
            },
            Source::Article { url } => format!("article {url}"),
        }
    }
}

impl Idea {
    pub fn render(&self) -> String {
        let mut lines = vec![
            format!("## {}", self.id),
            format!("- idea: {}", self.statement),
        ];
        lines.extend(
            self.sources
                .iter()
                .map(|s| format!("- source: {}", s.render())),
        );
        lines.extend(self.code.iter().map(|a| format!("- code: {}", a.render())));
        lines.join("\n")
    }

    pub fn upstream_symbols(&self) -> Vec<String> {
        self.sources
            .iter()
            .filter_map(|s| match s {
                Source::Code {
                    symbol: Some(sym), ..
                } => Some(sym.clone()),
                _ => None,
            })
            .collect()
    }
}

/// First DOI or arXiv identifier in a `CITATION.cff` or `codemeta.json`.
pub fn citation_identifier(text: &str) -> Option<String> {
    if let Some(m) = DOI.find(text) {
        return Some(format!("doi:{}", m.as_str().trim_end_matches(['.', ')'])));
    }
    ARXIV.captures(text).map(|c| format!("arXiv:{}", &c[1]))
}

#[derive(Debug, Clone, Serialize)]
pub struct AnchorCheck {
    pub idea: String,
    pub anchor: String,
    pub status: &'static str,
    pub detail: String,
}

/// Resolve every code anchor against `read(path)`; `others` lets moved code be re-found by hash.
pub fn check(
    manifest: &mut Manifest,
    read: &dyn Fn(&str) -> Option<String>,
    others: &dyn Fn() -> Vec<(String, String)>,
    fix: bool,
    rehash: bool,
) -> Vec<AnchorCheck> {
    let mut results = Vec::new();
    let mut corpus: Option<Vec<(String, String)>> = None;
    for idea in &mut manifest.ideas {
        for anchor in &mut idea.code {
            let label = anchor.label();
            let content = read(&anchor.path);
            let Some(hash) = anchor.hash.clone() else {
                let current = content
                    .as_deref()
                    .and_then(|c| anchors::current(&anchor.path, c, anchor.symbol.as_deref()));
                let (status, detail) = match (&current, rehash) {
                    (Some((h, lines, _)), true) => {
                        anchor.hash = Some(h.clone());
                        anchor.lines = Some(*lines);
                        ("anchored", format!("hash={h}"))
                    }
                    (Some(_), false) => (
                        "unanchored",
                        "no hash; run `memetics ideas --rehash`".into(),
                    ),
                    (None, _) => ("lost", "symbol or file not found".into()),
                };
                results.push(AnchorCheck {
                    idea: idea.id.clone(),
                    anchor: label,
                    status,
                    detail,
                });
                continue;
            };
            let mut resolution = anchors::resolve(
                &anchor.path,
                anchor.symbol.as_deref(),
                &hash,
                content.as_deref(),
                &[],
            );
            if resolution == Resolution::Lost && anchor.symbol.is_some() {
                let corpus = corpus.get_or_insert_with(others);
                resolution = anchors::resolve(
                    &anchor.path,
                    anchor.symbol.as_deref(),
                    &hash,
                    content.as_deref(),
                    corpus,
                );
            }
            let (status, detail) = match resolution {
                Resolution::Same { lines } => {
                    let stale = anchor.lines != Some(lines);
                    if fix || rehash {
                        anchor.lines = Some(lines);
                    }
                    (
                        "ok",
                        if stale {
                            format!("lines hint now {}-{}", lines.0, lines.1)
                        } else {
                            String::new()
                        },
                    )
                }
                Resolution::Moved {
                    path,
                    symbol,
                    lines,
                } => {
                    let detail =
                        format!("moved to {} {}", path, symbol.clone().unwrap_or_default());
                    if fix || rehash {
                        anchor.path = path;
                        anchor.symbol = symbol;
                        anchor.lines = Some(lines);
                    }
                    ("moved", detail)
                }
                Resolution::Changed { lines, hash } => {
                    if fix || rehash {
                        anchor.lines = Some(lines);
                    }
                    if rehash {
                        anchor.hash = Some(hash.clone());
                    }
                    (
                        "changed",
                        format!(
                            "content changed (now hash={hash}, lines {}-{})",
                            lines.0, lines.1
                        ),
                    )
                }
                Resolution::Lost => ("lost", "neither the symbol nor the hash was found".into()),
            };
            results.push(AnchorCheck {
                idea: idea.id.clone(),
                anchor: label,
                status,
                detail,
            });
        }
    }
    results
}

#[cfg(test)]
mod tests {
    use super::*;

    const TEXT: &str = "# Memetics\n\nIdeas in this repo.\n\n## bounded-eviction\n- idea: Evict the oldest entries in bounded batches.\n- source: code swh:1:rev:0123456789abcdef0123456789abcdef01234567;path=/src/cache/eviction.py;lines=10-40 repo=https://github.com/example/upstream symbol=Cache.evict hash=0123456789abcdef\n- source: paper doi:10.1145/3597503.3639187 section=\"3.2 Batching\"\n- source: paper arXiv:2510.22396\n- source: article https://example.com/eviction\n- code: src/cache.rs symbol=Cache::evict hash=fedcba9876543210 lines=5-7\n\n## second\n- idea: Another.\n- code: src/other.py\n";

    #[test]
    fn parses_multiple_sources_and_round_trips() {
        let manifest = Manifest::parse(TEXT).unwrap();
        assert_eq!(manifest.ideas.len(), 2);
        let idea = &manifest.ideas[0];
        assert_eq!(idea.sources.len(), 4);
        assert_eq!(
            idea.sources[0].path().as_deref(),
            Some("src/cache/eviction.py")
        );
        assert_eq!(idea.upstream_symbols(), ["Cache.evict"]);
        assert!(
            matches!(&idea.sources[1], Source::Paper { section: Some(s), .. } if s == "3.2 Batching")
        );
        assert_eq!(idea.code[0].lines, Some((5, 7)));
        assert_eq!(manifest.render(), TEXT);
    }

    #[test]
    fn rejects_malformed_manifests() {
        for bad in [
            "## x\n- idea: a\n",
            "## x\n- idea: a\n- code: ../escape.rs\n",
            "## x\n- idea: a\n- code: a.rs hash=xyz\n",
            "## x\n- idea: a\nfree prose\n- code: a.rs\n",
            "## x\n- idea: a\n- source: code swh:1:bad:00 \n- code: a.rs\n",
            "## x\n- idea: a\n- source: paper 10.1145/1\n- code: a.rs\n",
        ] {
            assert!(Manifest::parse(bad).is_err(), "{bad}");
        }
    }

    #[test]
    fn citation_identifiers() {
        assert_eq!(
            citation_identifier("cff-version: 1.2.0\ndoi: 10.5281/zenodo.1234567\n").as_deref(),
            Some("doi:10.5281/zenodo.1234567")
        );
        assert_eq!(
            citation_identifier("{\"identifier\": \"https://arxiv.org/abs/2510.22396v2\"}")
                .as_deref(),
            Some("arXiv:2510.22396v2")
        );
        assert_eq!(citation_identifier("title: none"), None);
    }

    #[test]
    fn check_reanchors_and_flags() {
        let code = "struct Cache;\nimpl Cache {\n    fn evict(&self) -> u8 { 1 }\n}\n";
        let mut manifest =
            Manifest::parse("## a\n- idea: x\n- code: src/cache.rs symbol=Cache::evict\n").unwrap();
        let read = |_: &str| Some(code.to_string());
        let none = Vec::new;
        assert_eq!(
            check(&mut manifest, &read, &none, false, false)[0].status,
            "unanchored"
        );
        assert_eq!(
            check(&mut manifest, &read, &none, false, true)[0].status,
            "anchored"
        );
        assert_eq!(manifest.ideas[0].code[0].lines, Some((3, 3)));
        assert_eq!(
            check(&mut manifest, &read, &none, false, false)[0].status,
            "ok"
        );
        let renamed = |_: &str| Some(code.replace("fn evict", "fn drop_oldest"));
        assert_eq!(
            check(&mut manifest, &renamed, &none, true, false)[0].status,
            "moved"
        );
        assert_eq!(
            manifest.ideas[0].code[0].symbol.as_deref(),
            Some("Cache::drop_oldest")
        );
        let edited = |_: &str| {
            Some(
                code.replace("fn evict", "fn drop_oldest")
                    .replace("{ 1 }", "{ 2 }"),
            )
        };
        assert_eq!(
            check(&mut manifest, &edited, &none, false, false)[0].status,
            "changed"
        );
    }
}
