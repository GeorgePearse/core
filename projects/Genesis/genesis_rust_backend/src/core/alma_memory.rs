use serde::{Deserialize, Serialize};
use std::collections::HashSet;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AlmaMemoryEntry {
    pub generation: usize,
    pub memory_type: String,
    pub patch_type: String,
    pub patch_name: String,
    pub patch_description: String,
    pub score_delta: f64,
    pub combined_score: f64,
    pub summary: String,
    pub keywords: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AlmaMemorySystem {
    pub enabled: bool,
    pub max_entries: usize,
    pub max_retrievals: usize,
    pub min_success_delta: f64,
    pub entries: Vec<AlmaMemoryEntry>,
}

impl AlmaMemorySystem {
    pub fn new(
        enabled: bool,
        max_entries: usize,
        max_retrievals: usize,
        min_success_delta: f64,
    ) -> Self {
        Self {
            enabled,
            max_entries: max_entries.max(1),
            max_retrievals: max_retrievals.max(1),
            min_success_delta,
            entries: Vec::new(),
        }
    }

    #[allow(clippy::too_many_arguments)]
    pub fn observe_outcome(
        &mut self,
        generation: usize,
        parent_score: f64,
        child_score: f64,
        correct: bool,
        patch_type: &str,
        patch_name: &str,
        patch_description: &str,
        diff_summary: &str,
        text_feedback: &str,
        error_message: &str,
    ) {
        if !self.enabled {
            return;
        }

        let score_delta = child_score - parent_score;
        let memory_type = if correct && score_delta >= self.min_success_delta {
            "success"
        } else {
            "failure"
        }
        .to_string();

        let summary = [
            patch_description,
            diff_summary,
            text_feedback,
            error_message,
        ]
        .iter()
        .filter(|s| !s.is_empty())
        .copied()
        .collect::<Vec<_>>()
        .join(" | ");

        let keywords = extract_keywords(&format!(
            "{} {} {} {} {} {}",
            patch_type, patch_name, patch_description, diff_summary, text_feedback, error_message
        ));

        self.entries.push(AlmaMemoryEntry {
            generation,
            memory_type,
            patch_type: patch_type.to_string(),
            patch_name: patch_name.to_string(),
            patch_description: patch_description.to_string(),
            score_delta,
            combined_score: child_score,
            summary,
            keywords,
        });

        self.entries
            .sort_by(|a, b| b.score_delta.abs().total_cmp(&a.score_delta.abs()));
        if self.entries.len() > self.max_entries {
            self.entries.truncate(self.max_entries);
        }
    }

    pub fn build_prompt_context(
        &self,
        current_generation: usize,
        parent_code: &str,
        parent_feedback: &str,
    ) -> Option<String> {
        if !self.enabled || self.entries.is_empty() {
            return None;
        }

        let context_keywords = extract_keywords(&format!("{} {}", parent_code, parent_feedback));
        let context_set: HashSet<String> = context_keywords.into_iter().collect();

        let mut scored = self
            .entries
            .iter()
            .map(|entry| {
                let overlap = entry
                    .keywords
                    .iter()
                    .filter(|k| context_set.contains(*k))
                    .count() as f64;
                let recency =
                    1.0 / (1.0 + current_generation.saturating_sub(entry.generation) as f64);
                let impact = entry.score_delta.abs();
                (2.0 * overlap + recency + impact, entry)
            })
            .collect::<Vec<_>>();

        scored.sort_by(|a, b| b.0.total_cmp(&a.0));
        let selected = scored
            .into_iter()
            .take(self.max_retrievals)
            .map(|(_, entry)| entry)
            .collect::<Vec<_>>();

        if selected.is_empty() {
            return None;
        }

        let mut out = String::from("# ALMA Long-Term Memory\n");
        let successes = selected
            .iter()
            .filter(|e| e.memory_type == "success")
            .collect::<Vec<_>>();
        let failures = selected
            .iter()
            .filter(|e| e.memory_type == "failure")
            .collect::<Vec<_>>();

        if !successes.is_empty() {
            out.push_str("## Reuse These Successful Patterns\n");
            for s in successes {
                out.push_str(&format!(
                    "- {} `{}` (delta {:+.4}): {}\n",
                    s.patch_type, s.patch_name, s.score_delta, s.summary
                ));
            }
        }

        if !failures.is_empty() {
            out.push_str("## Avoid These Failure Patterns\n");
            for f in failures {
                out.push_str(&format!(
                    "- {} `{}` (delta {:+.4}): {}\n",
                    f.patch_type, f.patch_name, f.score_delta, f.summary
                ));
            }
        }

        Some(out)
    }

    pub fn save_state(&self, path: &str) -> anyhow::Result<()> {
        if !self.enabled {
            return Ok(());
        }
        let payload = serde_json::to_string_pretty(self)?;
        std::fs::write(path, payload)?;
        Ok(())
    }

    pub fn load_state(&mut self, path: &str) -> bool {
        if !self.enabled {
            return false;
        }
        let Ok(raw) = std::fs::read_to_string(path) else {
            return false;
        };
        let Ok(parsed) = serde_json::from_str::<AlmaMemorySystem>(&raw) else {
            return false;
        };
        self.entries = parsed.entries;
        true
    }
}

fn extract_keywords(text: &str) -> Vec<String> {
    let stopwords: HashSet<&str> = [
        "the",
        "and",
        "for",
        "with",
        "that",
        "this",
        "from",
        "into",
        "code",
        "patch",
        "generation",
        "score",
        "delta",
        "result",
        "error",
    ]
    .iter()
    .copied()
    .collect();

    let mut seen = HashSet::new();
    let mut out = Vec::new();
    for token in text
        .split(|c: char| !c.is_alphanumeric() && c != '_')
        .map(|t| t.to_lowercase())
    {
        if token.len() < 3 || stopwords.contains(token.as_str()) || seen.contains(&token) {
            continue;
        }
        seen.insert(token.clone());
        out.push(token);
        if out.len() >= 30 {
            break;
        }
    }
    out
}
