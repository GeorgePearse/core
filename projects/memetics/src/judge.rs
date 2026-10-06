//! Idea-drift checks: did a commit that touched idea code keep, refine, replace or remove the idea?
//!
//! A cheap structural check runs first (normalised tree-sitter hashes, plus difftastic when
//! installed); the judge is called only when the normalised code changed. Jev's typed choice API
//! is the default judge; any OpenAI-compatible chat model can replace it.

use crate::anchors::{self, Resolution};
use crate::db::{Store, now};
use crate::error::{Result, invalid, other};
use crate::git::run_with_timeout;
use crate::ideas::{Anchor, Idea, MANIFEST, Manifest};
use crate::model::Chat;
use reqwest::blocking::Client;
use rusqlite::params;
use serde::Serialize;
use serde_json::{Map, Value, json};
use std::path::{Path, PathBuf};
use std::process::Command;
use std::time::Duration;

pub const CHOICES: [&str; 4] = [
    "same_idea",
    "refines_idea",
    "different_idea",
    "removes_idea",
];
const EMPTY_TREE: &str = "4b825dc642cb6eb9a060e54bf8d69288fbee4904";
const SNIPPET_LIMIT: usize = 12_000;

#[derive(Debug, Clone, Serialize)]
pub struct JudgedAnchor {
    pub id: String,
    pub path: String,
    pub symbol: Option<String>,
    pub before: String,
    pub after: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct Hunk {
    pub id: String,
    pub anchor: String,
    pub text: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct JudgeRequest {
    pub idea_id: String,
    pub statement: String,
    pub upstream_symbols: Vec<String>,
    pub anchors: Vec<JudgedAnchor>,
    pub hunks: Vec<Hunk>,
}

/// A judge returns `{choice, confidence, reason, evidence: {anchor, hunks, upstream_symbol}}`.
pub trait Judge {
    fn name(&self) -> String;
    fn judge(&self, request: &JudgeRequest) -> Result<Value>;
}

#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct Verdict {
    pub idea: String,
    pub choice: String,
    pub confidence: f64,
    pub reason: String,
    pub evidence: Value,
    /// `cheap` (structural check, no judge call) or `judge`.
    pub method: String,
    pub judge: String,
    pub status: String,
    pub note: String,
}

fn clip(text: &str) -> String {
    if text.len() <= SNIPPET_LIMIT {
        return text.to_string();
    }
    let mut end = SNIPPET_LIMIT;
    while !text.is_char_boundary(end) {
        end -= 1;
    }
    format!("{}\n…[truncated]", &text[..end])
}

impl JudgeRequest {
    pub fn state(&self) -> String {
        let mut out = vec![format!("Idea `{}`: {}", self.idea_id, self.statement)];
        if !self.upstream_symbols.is_empty() {
            out.push(format!(
                "Upstream symbols this idea follows: {}",
                self.upstream_symbols.join(", ")
            ));
        }
        for a in &self.anchors {
            out.push(format!(
                "\nAnchor {} — {} {}\n--- before ---\n{}\n--- after ---\n{}",
                a.id,
                a.path,
                a.symbol.as_deref().unwrap_or("(whole file)"),
                clip(&a.before),
                a.after
                    .as_deref()
                    .map(clip)
                    .unwrap_or_else(|| "(removed: symbol and hash not found)".into())
            ));
        }
        for h in &self.hunks {
            out.push(format!(
                "\nHunk {} (anchor {}):\n{}",
                h.id,
                h.anchor,
                clip(&h.text)
            ));
        }
        out.join("\n")
    }
}

/// Reject verdicts that do not cite the evidence they were judged on.
pub fn validate_verdict(
    request: &JudgeRequest,
    raw: &Value,
) -> Result<(String, f64, String, Value)> {
    let choice = raw["choice"]
        .as_str()
        .filter(|c| CHOICES.contains(c))
        .ok_or_else(|| other("judge returned no valid choice"))?;
    let confidence = raw["confidence"]
        .as_f64()
        .filter(|c| (0.0..=1.0).contains(c))
        .ok_or_else(|| other("judge returned no confidence in [0, 1]"))?;
    let evidence = &raw["evidence"];
    let missing = |what: &str| other(format!("judge verdict lacks evidence: {what}"));
    let anchor = evidence["anchor"]
        .as_str()
        .filter(|a| request.anchors.iter().any(|x| x.id == *a))
        .ok_or_else(|| missing("anchor id"))?;
    let hunks: Vec<String> = evidence["hunks"]
        .as_array()
        .into_iter()
        .flatten()
        .filter_map(|h| h.as_str().map(String::from))
        .collect();
    if hunks.is_empty()
        || !hunks
            .iter()
            .all(|h| request.hunks.iter().any(|x| &x.id == h))
    {
        return Err(missing("judged hunk ids"));
    }
    let mut cited = json!({"anchor": anchor, "hunks": hunks});
    if !request.upstream_symbols.is_empty() {
        let upstream = evidence["upstream_symbol"]
            .as_str()
            .filter(|s| request.upstream_symbols.iter().any(|x| x == s))
            .ok_or_else(|| missing("upstream symbol"))?;
        cited["upstream_symbol"] = upstream.into();
    }
    let reason = raw["reason"].as_str().unwrap_or_default().to_string();
    Ok((choice.to_string(), confidence, reason, cited))
}

/// Jev through the Vercel AI Gateway evaluation-model protocol: typed choices, calibrated probabilities.
pub struct JevJudge {
    pub base: String,
    pub model: String,
    pub key: String,
    client: Client,
}

impl JevJudge {
    pub fn new(base: &str, model: &str, key: &str) -> Self {
        JevJudge {
            base: base.trim_end_matches('/').into(),
            model: model.into(),
            key: key.into(),
            client: Client::builder()
                .timeout(Duration::from_secs(60))
                .build()
                .expect("HTTP client builds"),
        }
    }
}

fn options(pairs: impl IntoIterator<Item = (String, String)>) -> Value {
    let mut map: Map<String, Value> = pairs
        .into_iter()
        .map(|(k, v)| (k, Value::String(v)))
        .collect();
    map.insert("none".into(), "nothing here supports the verdict".into());
    Value::Object(map)
}

impl Judge for JevJudge {
    fn name(&self) -> String {
        self.model.clone()
    }

    fn judge(&self, request: &JudgeRequest) -> Result<Value> {
        let mut questions = json!({
            "verdict": {"type": "choice",
                "instructions": "Compare the before and after code of the anchors against the stated idea. Does the after code still implement the same idea?",
                "criteria": {
                    "same_idea": "Same idea; the change is cosmetic (renames, formatting, restructuring with identical behaviour).",
                    "refines_idea": "Same idea, improved or extended: an optimisation, edge-case fix or generalisation of the same approach.",
                    "different_idea": "The code now implements a different approach or algorithm than the stated idea.",
                    "removes_idea": "The idea is no longer implemented: the code was deleted or reduced so the idea is gone."}},
            "anchor": {"type": "choice", "instructions": "Which anchor's change most determines the verdict?",
                "criteria": options(request.anchors.iter().map(|a| (a.id.clone(), format!("{} {}", a.path, a.symbol.clone().unwrap_or_default()))))},
            "hunk": {"type": "choice", "instructions": "Which diff hunk most determines the verdict?",
                "criteria": options(request.hunks.iter().map(|h| (h.id.clone(), format!("hunk in anchor {}", h.anchor))))},
        });
        if !request.upstream_symbols.is_empty() {
            questions["upstream"] = json!({"type": "choice", "instructions": "Which upstream symbol does this idea follow?",
                "criteria": options(request.upstream_symbols.iter().map(|s| (s.clone(), format!("upstream {s}"))))});
        }
        let response = self
            .client
            .post(format!("{}/evaluation-model", self.base))
            .bearer_auth(&self.key)
            .header("ai-gateway-auth-method", "api-key")
            .header("ai-gateway-protocol-version", "0.0.1")
            .header("ai-evaluation-model-specification-version", "4")
            .header("ai-model-id", &self.model)
            .json(&json!({"state": request.state(), "questions": questions}))
            .send()?;
        let status = response.status();
        let body = response.text()?;
        if !status.is_success() {
            return Err(other(format!(
                "Jev HTTP {}: {}",
                status.as_u16(),
                body.chars().take(400).collect::<String>()
            )));
        }
        let data: Value = serde_json::from_str(&body)?;
        let answers = &data["answers"];
        let pick = |q: &str| {
            answers[q]["choice"]
                .as_str()
                .filter(|c| *c != "none")
                .map(String::from)
        };
        let choice = pick("verdict");
        let probability = choice
            .as_ref()
            .and_then(|c| answers["verdict"]["probabilities"][c].as_f64());
        let confidence = data["providerMetadata"]["typesafe"]["confidence"]["verdict"]
            .as_f64()
            .or(probability);
        Ok(json!({
            "choice": choice,
            "confidence": confidence,
            "reason": format!("Jev probabilities {}", answers["verdict"]["probabilities"]),
            "evidence": {"anchor": pick("anchor"), "hunks": pick("hunk").map(|h| vec![h]).unwrap_or_default(),
                "upstream_symbol": pick("upstream")},
            "usage": data["usage"],
        }))
    }
}

/// Any OpenAI-compatible chat model, e.g. OpenRouter's `typesafe/jev-router`.
pub struct ChatJudge {
    pub chat: Chat,
}

const CHAT_SYSTEM: &str = r#"You judge whether a code change keeps a recorded idea. Reply with one JSON object:
{"choice":"same_idea|refines_idea|different_idea|removes_idea","confidence":0.0-1.0,"reason":"one line",
 "evidence":{"anchor":"anchor id","hunks":["hunk ids you judged"],"upstream_symbol":"one of the upstream symbols, if any are listed"}}
same_idea: cosmetic change. refines_idea: same approach, improved. different_idea: a different approach
or algorithm. removes_idea: the idea is gone. Cite only ids that appear in the input."#;

impl Judge for ChatJudge {
    fn name(&self) -> String {
        self.chat.name.clone()
    }

    fn judge(&self, request: &JudgeRequest) -> Result<Value> {
        let messages = [
            json!({"role": "system", "content": CHAT_SYSTEM}),
            json!({"role": "user", "content": request.state()}),
        ];
        Ok(self.chat.complete(&messages, 2_000)?.content)
    }
}

/// `MEMETICS_JUDGE=jev` (default, Vercel AI Gateway) or `chat` (OpenAI-compatible, default OpenRouter jev-router).
pub fn from_env() -> Result<Box<dyn Judge>> {
    let var = |k: &str| std::env::var(k).ok().filter(|v| !v.is_empty());
    match var("MEMETICS_JUDGE").as_deref().unwrap_or("jev") {
        "jev" => {
            let key = var("MEMETICS_JUDGE_API_KEY")
                .or_else(|| var("AI_GATEWAY_API_KEY"))
                .ok_or_else(|| {
                    other("set MEMETICS_JUDGE_API_KEY or AI_GATEWAY_API_KEY for the Jev judge")
                })?;
            Ok(Box::new(JevJudge::new(
                &var("MEMETICS_JUDGE_BASE_URL")
                    .unwrap_or_else(|| "https://ai-gateway.vercel.sh/v4/ai".into()),
                &var("MEMETICS_JUDGE_MODEL").unwrap_or_else(|| "typesafe-ai/jev".into()),
                &key,
            )))
        }
        "chat" => {
            let key = var("MEMETICS_JUDGE_API_KEY")
                .or_else(|| var("OPENROUTER_API_KEY"))
                .ok_or_else(|| {
                    other("set MEMETICS_JUDGE_API_KEY or OPENROUTER_API_KEY for the chat judge")
                })?;
            let base = var("MEMETICS_JUDGE_BASE_URL")
                .unwrap_or_else(|| "https://openrouter.ai/api/v1".into());
            let mut chat = Chat::new(
                &base,
                &var("MEMETICS_JUDGE_MODEL").unwrap_or_else(|| "typesafe/jev-router".into()),
                &key,
            );
            chat.extra.insert("temperature".into(), 0.into());
            if base.contains("openrouter.ai") {
                chat.extra
                    .insert("reasoning".into(), json!({"effort": "low"}));
            }
            Ok(Box::new(ChatJudge { chat }))
        }
        other_name => Err(invalid(format!(
            "unknown MEMETICS_JUDGE {other_name}; use jev or chat"
        ))),
    }
}

#[derive(Debug, Clone)]
pub enum Target {
    Commit(String),
    Range(String, String),
    Staged,
}

impl Target {
    pub fn parse(value: Option<&str>, staged: bool) -> Result<Target> {
        match (value, staged) {
            (_, true) => Ok(Target::Staged),
            (Some(v), false) => Ok(match v.split_once("..") {
                Some((a, b)) => Target::Range(
                    a.into(),
                    if b.is_empty() {
                        "HEAD".into()
                    } else {
                        b.into()
                    },
                ),
                None => Target::Commit(v.into()),
            }),
            (None, false) => Err(invalid("give a revision, a base..head range, or --staged")),
        }
    }
}

pub struct CheckOptions {
    pub repo: PathBuf,
    pub target: Target,
    pub threshold: f64,
    pub strict_refines: bool,
    pub update_anchors: bool,
}

#[derive(Debug, Clone, Default, Serialize)]
pub struct Report {
    pub revision: String,
    pub verdicts: Vec<Verdict>,
    pub anchor_updates: Vec<String>,
    pub notes: Vec<String>,
    pub errors: Vec<String>,
}

#[derive(Debug, Clone)]
struct DiffHunk {
    old_start: usize,
    old_count: usize,
    text: String,
}

#[derive(Debug, Clone, Default)]
struct FileDiff {
    old: Option<String>,
    new: Option<String>,
    hunks: Vec<DiffHunk>,
}

fn git(repo: &Path, args: &[&str]) -> Result<crate::git::Output> {
    let mut command = Command::new("git");
    command.args(args).current_dir(repo);
    run_with_timeout(&mut command, Duration::from_secs(120), None)
}

fn git_text(repo: &Path, args: &[&str]) -> Result<String> {
    let out = git(repo, args)?;
    if out.code != Some(0) {
        return Err(other(format!(
            "git {} failed: {}",
            args.join(" "),
            String::from_utf8_lossy(&out.stderr).trim()
        )));
    }
    Ok(out.text().trim_end().to_string())
}

fn parse_range(spec: &str) -> (usize, usize) {
    let (start, count) = spec.split_once(',').unwrap_or((spec, "1"));
    (start.parse().unwrap_or(0), count.parse().unwrap_or(1))
}

fn strip_prefix(path: &str, prefix: &str) -> Option<String> {
    (path != "/dev/null").then(|| path.strip_prefix(prefix).unwrap_or(path).to_string())
}

fn parse_diff(text: &str) -> Vec<FileDiff> {
    let mut files: Vec<FileDiff> = Vec::new();
    for line in text.lines() {
        if let Some(rest) = line.strip_prefix("diff --git ") {
            let (a, b) = rest.split_once(" b/").unwrap_or((rest, rest));
            files.push(FileDiff {
                old: Some(a.trim_start_matches("a/").to_string()),
                new: Some(b.to_string()),
                hunks: vec![],
            });
            continue;
        }
        let Some(file) = files.last_mut() else {
            continue;
        };
        if let Some(hunk) = file.hunks.last_mut()
            && !line.starts_with("@@ ")
        {
            hunk.text.push('\n');
            hunk.text.push_str(line);
            continue;
        }
        if let Some(p) = line.strip_prefix("--- ") {
            file.old = strip_prefix(p, "a/");
        } else if let Some(p) = line.strip_prefix("+++ ") {
            file.new = strip_prefix(p, "b/");
        } else if let Some(p) = line.strip_prefix("rename from ") {
            file.old = Some(p.into());
        } else if let Some(p) = line.strip_prefix("rename to ") {
            file.new = Some(p.into());
        } else if line.starts_with("new file mode") {
            file.old = None;
        } else if line.starts_with("deleted file mode") {
            file.new = None;
        } else if let Some(rest) = line.strip_prefix("@@ -") {
            let old = rest.split_whitespace().next().unwrap_or_default();
            let (old_start, old_count) = parse_range(old);
            file.hunks.push(DiffHunk {
                old_start,
                old_count,
                text: line.to_string(),
            });
        }
    }
    files
}

fn overlaps(hunk: &DiffHunk, (a, b): (usize, usize)) -> bool {
    if hunk.old_count == 0 {
        // Pure insertion after `old_start`.
        return a <= hunk.old_start && hunk.old_start < b;
    }
    let end = hunk.old_start + hunk.old_count - 1;
    hunk.old_start <= b && a <= end
}

/// `Some(true)` when difftastic reports no syntactic change; `None` when difft is unavailable.
fn difftastic_unchanged(path: &str, before: &str, after: &str) -> Option<bool> {
    let dir = tempfile::tempdir().ok()?;
    let extension = path.rsplit_once('.').map(|(_, e)| e).unwrap_or("txt");
    let (a, b) = (
        dir.path().join(format!("before.{extension}")),
        dir.path().join(format!("after.{extension}")),
    );
    std::fs::write(&a, before).ok()?;
    std::fs::write(&b, after).ok()?;
    let mut command = Command::new("difft");
    command
        .args(["--check-only", "--exit-code"])
        .arg(&a)
        .arg(&b);
    let out = run_with_timeout(&mut command, Duration::from_secs(30), None).ok()?;
    match out.code {
        Some(0) => Some(true),
        Some(1) => Some(false),
        _ => None,
    }
}

/// CI policy: fail only on confident different/removes without a manifest amendment.
pub fn decide(
    choice: &str,
    confidence: f64,
    threshold: f64,
    amended: bool,
    strict_refines: bool,
) -> (&'static str, String) {
    match choice {
        "same_idea" => ("pass", String::new()),
        "refines_idea" if amended => ("pass", "memetics.md amended for this idea".into()),
        "refines_idea" if strict_refines => (
            "fail",
            "refinement needs a one-line amendment to memetics.md (--strict-refines)".into(),
        ),
        "refines_idea" => ("warn", "idea refined; consider amending memetics.md".into()),
        _ if amended => (
            "pass",
            "memetics.md updated for this idea in the same change".into(),
        ),
        _ if confidence >= threshold => (
            "fail",
            "update memetics.md for this idea or restore it".into(),
        ),
        _ => (
            "warn",
            format!("below the {threshold} confidence threshold"),
        ),
    }
}

fn manifest_key(idea: Option<&Idea>) -> Option<String> {
    idea.map(|i| {
        let mut copy = i.clone();
        copy.code.iter_mut().for_each(|a| a.lines = None);
        copy.render()
    })
}

struct Sides {
    repo: PathBuf,
    base: String,
    head: Option<String>,
}

impl Sides {
    fn read_base(&self, path: &str) -> Option<String> {
        git_text_raw(&self.repo, &format!("{}:{path}", self.base))
    }
    fn read_head(&self, path: &str) -> Option<String> {
        match &self.head {
            Some(head) => git_text_raw(&self.repo, &format!("{head}:{path}")),
            None => git_text_raw(&self.repo, &format!(":{path}")),
        }
    }
}

fn git_text_raw(repo: &Path, spec: &str) -> Option<String> {
    let out = git(repo, &["cat-file", "blob", spec]).ok()?;
    (out.code == Some(0)).then(|| String::from_utf8_lossy(&out.stdout).into_owned())
}

pub fn check_commit(
    options: &CheckOptions,
    judge: Option<&dyn Judge>,
    store: Option<&Store>,
) -> Result<Report> {
    let repo = &options.repo;
    let resolve = |rev: &str| {
        git_text(
            repo,
            &[
                "rev-parse",
                "--verify",
                "--quiet",
                &format!("{rev}^{{commit}}"),
            ],
        )
    };
    let (base, head) = match &options.target {
        Target::Commit(rev) => {
            let head = resolve(rev)?;
            (
                resolve(&format!("{head}^")).unwrap_or_else(|_| EMPTY_TREE.into()),
                Some(head),
            )
        }
        Target::Range(a, b) => (resolve(a)?, Some(resolve(b)?)),
        Target::Staged => (resolve("HEAD").unwrap_or_else(|_| EMPTY_TREE.into()), None),
    };
    let revision = match &head {
        Some(h) => format!("{base}..{h}"),
        None => format!("{base}..index:{}", git_text(repo, &["write-tree"])?),
    };
    let sides = Sides {
        repo: repo.clone(),
        base: base.clone(),
        head: head.clone(),
    };
    let mut report = Report {
        revision: revision.clone(),
        ..Default::default()
    };
    let Some(base_text) = sides.read_base(MANIFEST) else {
        report.notes.push(format!(
            "no {MANIFEST} at the base revision; nothing to check"
        ));
        return Ok(report);
    };
    let base_manifest = Manifest::parse(&base_text)?;
    let head_manifest = match sides.read_head(MANIFEST) {
        Some(text) => Manifest::parse(&text)?,
        None => Manifest::default(),
    };
    let mut diff_args = vec!["diff", "-U0", "-M", "--no-color", "--no-ext-diff"];
    if head.is_none() {
        diff_args.push("--cached");
    }
    diff_args.push(&base);
    if let Some(h) = &head {
        diff_args.push(h);
    }
    let diffs = parse_diff(&git_text(repo, &diff_args)?);
    let changed_after: Vec<(String, String)> = diffs
        .iter()
        .filter_map(|d| d.new.clone())
        .filter(|p| anchors::supported(p))
        .filter_map(|p| sides.read_head(&p).map(|c| (p, c)))
        .collect();
    let mut updates: Vec<(String, Anchor, Anchor)> = Vec::new();
    for idea in &base_manifest.ideas {
        let mut judged = Vec::new();
        let mut hunks = Vec::new();
        let mut cheap = Vec::new();
        for anchor in &idea.code {
            let Some(base_content) = sides.read_base(&anchor.path) else {
                continue;
            };
            let Some((hash, lines, before_text)) =
                anchors::current(&anchor.path, &base_content, anchor.symbol.as_deref())
            else {
                report.notes.push(format!(
                    "{}: {} not found at the base revision",
                    idea.id,
                    anchor.label()
                ));
                continue;
            };
            let Some(diff) = diffs
                .iter()
                .find(|d| d.old.as_deref() == Some(anchor.path.as_str()))
            else {
                continue;
            };
            let touching: Vec<&DiffHunk> =
                diff.hunks.iter().filter(|h| overlaps(h, lines)).collect();
            let renamed_file = diff.new.as_deref().filter(|n| *n != anchor.path);
            if touching.is_empty() {
                if let Some(new_path) = renamed_file {
                    let mut moved = anchor.clone();
                    moved.path = new_path.into();
                    updates.push((idea.id.clone(), anchor.clone(), moved));
                    cheap.push(format!("{} file renamed to {new_path}", anchor.label()));
                }
                continue;
            }
            let head_path = diff.new.clone().unwrap_or_else(|| anchor.path.clone());
            let head_content = diff.new.as_ref().and_then(|p| sides.read_head(p));
            let resolution = anchors::resolve(
                &head_path,
                anchor.symbol.as_deref(),
                &hash,
                head_content.as_deref(),
                &changed_after,
            );
            let after_text = match &resolution {
                Resolution::Same { lines } => {
                    if *lines != lines_hint(anchor) || head_path != anchor.path {
                        let mut moved = anchor.clone();
                        moved.path = head_path.clone();
                        moved.lines = Some(*lines);
                        updates.push((idea.id.clone(), anchor.clone(), moved));
                    }
                    cheap.push(format!("{}: normalised code unchanged", anchor.label()));
                    continue;
                }
                Resolution::Moved {
                    path,
                    symbol,
                    lines,
                } => {
                    let mut moved = anchor.clone();
                    moved.path = path.clone();
                    moved.symbol = symbol.clone();
                    moved.lines = Some(*lines);
                    updates.push((idea.id.clone(), anchor.clone(), moved.clone()));
                    cheap.push(format!(
                        "{}: moved or renamed to {}",
                        anchor.label(),
                        moved.label()
                    ));
                    continue;
                }
                Resolution::Changed { .. } => head_content
                    .as_deref()
                    .and_then(|c| anchors::current(&head_path, c, anchor.symbol.as_deref()))
                    .map(|(_, _, text)| text),
                Resolution::Lost => None,
            };
            if let Some(after) = &after_text
                && difftastic_unchanged(&anchor.path, &before_text, after) == Some(true)
            {
                cheap.push(format!(
                    "{}: difftastic reports no syntactic change",
                    anchor.label()
                ));
                continue;
            }
            let id = format!("a{}", judged.len() + 1);
            for h in touching {
                hunks.push(Hunk {
                    id: format!("h{}", hunks.len() + 1),
                    anchor: id.clone(),
                    text: h.text.clone(),
                });
            }
            judged.push(JudgedAnchor {
                id,
                path: anchor.path.clone(),
                symbol: anchor.symbol.clone(),
                before: before_text,
                after: after_text,
            });
        }
        if judged.is_empty() && cheap.is_empty() {
            continue;
        }
        let amended = manifest_key(Some(idea)) != manifest_key(head_manifest.idea(&idea.id));
        let verdict: Result<Verdict> = if judged.is_empty() {
            Ok(Verdict {
                idea: idea.id.clone(),
                choice: "same_idea".into(),
                confidence: 1.0,
                reason: cheap.join("; "),
                evidence: json!({"cheap": cheap}),
                method: "cheap".into(),
                judge: String::new(),
                status: String::new(),
                note: String::new(),
            })
        } else {
            let request = JudgeRequest {
                idea_id: idea.id.clone(),
                statement: idea.statement.clone(),
                upstream_symbols: idea.upstream_symbols(),
                anchors: judged,
                hunks,
            };
            cached(store, &revision, &idea.id)
                .map(Ok)
                .unwrap_or_else(|| {
                    let judge = judge
                        .ok_or_else(|| other("idea code changed and no judge is configured"))?;
                    let raw = judge.judge(&request)?;
                    let (choice, confidence, reason, evidence) = validate_verdict(&request, &raw)?;
                    Ok(Verdict {
                        idea: idea.id.clone(),
                        choice,
                        confidence,
                        reason,
                        evidence,
                        method: "judge".into(),
                        judge: judge.name(),
                        status: String::new(),
                        note: String::new(),
                    })
                })
        };
        match verdict {
            Ok(mut v) => {
                let (status, note) = decide(
                    &v.choice,
                    v.confidence,
                    options.threshold,
                    amended,
                    options.strict_refines,
                );
                v.status = status.into();
                v.note = note;
                if let Some(store) = store {
                    store.execute(
                        "INSERT OR REPLACE INTO idea_verdicts(revision,idea_id,choice,confidence,reason,judge,method,evidence,created)
                        VALUES(?,?,?,?,?,?,?,?,?)",
                        params![revision, v.idea, v.choice, v.confidence, v.reason, v.judge, v.method, v.evidence.to_string(), now()],
                    )?;
                }
                report.verdicts.push(v);
            }
            Err(e) => {
                report.errors.push(format!("{}: {e}", idea.id));
                report.verdicts.push(Verdict {
                    idea: idea.id.clone(),
                    choice: "unknown".into(),
                    confidence: 0.0,
                    reason: e.to_string(),
                    evidence: Value::Null,
                    method: "judge".into(),
                    judge: judge.map(|j| j.name()).unwrap_or_default(),
                    status: "error".into(),
                    note: "a verdict without evidence is an error, not a pass".into(),
                });
            }
        }
    }
    for (idea, old, new) in &updates {
        report
            .anchor_updates
            .push(format!("{idea}: {} -> {}", old.render(), new.render()));
    }
    if options.update_anchors && !updates.is_empty() {
        let path = repo.join(MANIFEST);
        let mut manifest = Manifest::parse(&std::fs::read_to_string(&path)?)?;
        for (idea, old, new) in &updates {
            if let Some(entry) = manifest.ideas.iter_mut().find(|i| &i.id == idea) {
                for anchor in entry
                    .code
                    .iter_mut()
                    .filter(|a| a.path == old.path && a.symbol == old.symbol)
                {
                    *anchor = Anchor {
                        hash: anchor.hash.clone(),
                        ..new.clone()
                    };
                }
            }
        }
        std::fs::write(&path, manifest.render())?;
        if matches!(options.target, Target::Staged) {
            git_text(repo, &["add", "--", MANIFEST])?;
        }
        report
            .notes
            .push(format!("updated {} anchor(s) in {MANIFEST}", updates.len()));
    }
    Ok(report)
}

fn lines_hint(anchor: &Anchor) -> (usize, usize) {
    anchor.lines.unwrap_or((0, 0))
}

fn cached(store: Option<&Store>, revision: &str, idea: &str) -> Option<Verdict> {
    let row = store?
        .one(
            "SELECT * FROM idea_verdicts WHERE revision=? AND idea_id=? AND method='judge'",
            params![revision, idea],
        )
        .ok()??;
    Some(Verdict {
        idea: idea.into(),
        choice: crate::db::text(&row, "choice"),
        confidence: row["confidence"].as_f64().unwrap_or(0.0),
        reason: crate::db::text(&row, "reason"),
        evidence: serde_json::from_str(&crate::db::text(&row, "evidence")).unwrap_or(Value::Null),
        method: "judge".into(),
        judge: format!("{} (cached)", crate::db::text(&row, "judge")),
        status: String::new(),
        note: String::new(),
    })
}

impl Report {
    pub fn exit_code(&self) -> i32 {
        if !self.errors.is_empty() {
            2
        } else if self.verdicts.iter().any(|v| v.status == "fail") {
            1
        } else {
            0
        }
    }

    pub fn render(&self, format: &str) -> String {
        match format {
            "json" => serde_json::to_string_pretty(self).unwrap_or_default(),
            "markdown" => {
                if self.verdicts.is_empty() && self.anchor_updates.is_empty() {
                    return String::new();
                }
                let mut out = vec![
                    "### Memetics idea-drift check".to_string(),
                    String::new(),
                    format!("Revision `{}`", self.revision),
                    String::new(),
                    "| Idea | Verdict | Confidence | Via | Status | Note |".into(),
                    "|---|---|---|---|---|---|".into(),
                ];
                for v in &self.verdicts {
                    let via = if v.method == "cheap" {
                        "structural check".to_string()
                    } else {
                        v.judge.clone()
                    };
                    out.push(format!(
                        "| `{}` | {} | {:.2} | {via} | **{}** | {} |",
                        v.idea, v.choice, v.confidence, v.status, v.note
                    ));
                }
                out.push(String::new());
                for v in &self.verdicts {
                    out.push(format!("<details><summary>{} evidence</summary>\n\n{}\n\n```json\n{}\n```\n</details>", v.idea, v.reason, v.evidence));
                }
                for u in &self.anchor_updates {
                    out.push(format!("- anchor update: `{u}`"));
                }
                out.join("\n")
            }
            _ => {
                let mut out = Vec::new();
                for v in &self.verdicts {
                    let via = if v.method == "cheap" {
                        "structural check".to_string()
                    } else {
                        v.judge.clone()
                    };
                    out.push(format!(
                        "[{}] {}: {} ({:.2}, {via}) {}",
                        v.status.to_uppercase(),
                        v.idea,
                        v.choice,
                        v.confidence,
                        v.note
                    ));
                    if !v.reason.is_empty() {
                        out.push(format!("    {}", v.reason));
                    }
                    if v.method == "judge" && !v.evidence.is_null() {
                        out.push(format!("    evidence: {}", v.evidence));
                    }
                }
                out.extend(
                    self.anchor_updates
                        .iter()
                        .map(|u| format!("anchor update: {u}")),
                );
                out.extend(self.notes.iter().map(|n| format!("note: {n}")));
                out.extend(self.errors.iter().map(|e| format!("error: {e}")));
                if out.is_empty() {
                    out.push("no idea code touched".into());
                }
                out.join("\n")
            }
        }
    }
}

const HOOK_MARKER: &str = "# memetics: idea-drift check";

pub fn install_hook(repo: &Path, kind: &str, force: bool) -> Result<PathBuf> {
    let command = match kind {
        "pre-commit" => "check-commit --staged --update-anchors",
        "post-commit" => "check-commit HEAD",
        _ => return Err(invalid("hook must be pre-commit or post-commit")),
    };
    let hooks = PathBuf::from(git_text(repo, &["rev-parse", "--git-path", "hooks"])?);
    let hooks = if hooks.is_absolute() {
        hooks
    } else {
        repo.join(hooks)
    };
    std::fs::create_dir_all(&hooks)?;
    let path = hooks.join(kind);
    if let Ok(existing) = std::fs::read_to_string(&path)
        && !existing.contains(HOOK_MARKER)
        && !force
    {
        return Err(invalid(format!(
            "{} exists and was not installed by memetics; use --force",
            path.display()
        )));
    }
    let exe = std::env::current_exe()
        .map(|p| p.display().to_string())
        .unwrap_or_else(|_| "memetics".into());
    let script = format!(
        "#!/bin/sh\n{HOOK_MARKER} (installed by `memetics install-hook`)\nMEMETICS=\"$(command -v memetics || echo '{exe}')\"\nexec \"$MEMETICS\" {command}\n"
    );
    std::fs::write(&path, script)?;
    use std::os::unix::fs::PermissionsExt;
    std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o755))?;
    Ok(path)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn diff_parsing_and_overlap() {
        let diff = "diff --git a/src/a.rs b/src/b.rs\nsimilarity index 90%\nrename from src/a.rs\nrename to src/b.rs\n--- a/src/a.rs\n+++ b/src/b.rs\n@@ -3,2 +3,3 @@ fn x\n-a\n-b\n+c\n+d\n+e\n@@ -10,0 +12 @@\n+f\ndiff --git a/new.py b/new.py\nnew file mode 100644\n--- /dev/null\n+++ b/new.py\n@@ -0,0 +1 @@\n+x\n";
        let files = parse_diff(diff);
        assert_eq!(files.len(), 2);
        assert_eq!(
            (files[0].old.as_deref(), files[0].new.as_deref()),
            (Some("src/a.rs"), Some("src/b.rs"))
        );
        assert_eq!(files[0].hunks.len(), 2);
        assert!(files[0].hunks[0].text.ends_with("+e"));
        assert_eq!(files[1].old, None);
        let (edit, insert) = (&files[0].hunks[0], &files[0].hunks[1]);
        assert!(overlaps(edit, (4, 8)) && overlaps(edit, (1, 3)) && !overlaps(edit, (5, 9)));
        assert!(
            overlaps(insert, (9, 11)) && !overlaps(insert, (10, 10)) && !overlaps(insert, (11, 20))
        );
    }

    #[test]
    fn policy() {
        assert_eq!(decide("different_idea", 0.9, 0.7, false, false).0, "fail");
        assert_eq!(decide("removes_idea", 0.9, 0.7, true, false).0, "pass");
        assert_eq!(decide("different_idea", 0.5, 0.7, false, false).0, "warn");
        assert_eq!(decide("refines_idea", 0.99, 0.7, false, false).0, "warn");
        assert_eq!(decide("refines_idea", 0.99, 0.7, false, true).0, "fail");
        assert_eq!(decide("refines_idea", 0.99, 0.7, true, true).0, "pass");
        assert_eq!(decide("same_idea", 0.99, 0.7, false, true).0, "pass");
    }
}
