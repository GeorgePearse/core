use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GepaTrace {
    pub generation: usize,
    pub parent_score: f64,
    pub child_score: f64,
    pub score_delta: f64,
    pub patch_type: String,
    pub patch_name: String,
    pub patch_description: String,
    pub diff_summary: String,
    pub candidate_id: Option<usize>,
    pub candidate_instruction: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GepaStyleOptimizer {
    pub enabled: bool,
    pub num_fewshot_traces: usize,
    pub max_traces: usize,
    pub min_improvement: f64,
    pub exploration_weight: f64,
    pub candidate_instructions: Vec<String>,
    pub total_trials: usize,
    pub candidate_trials: Vec<usize>,
    pub candidate_total_delta: Vec<f64>,
    pub traces: Vec<GepaTrace>,
}

impl GepaStyleOptimizer {
    pub fn new(
        enabled: bool,
        num_fewshot_traces: usize,
        max_traces: usize,
        min_improvement: f64,
        exploration_weight: f64,
        candidate_instructions: Option<Vec<String>>,
    ) -> Self {
        let candidates = candidate_instructions.unwrap_or_else(|| {
            vec![
                "Prioritize algorithm-level improvements over cosmetic refactors.".to_string(),
                "Keep edits minimal and verify invariants before major changes.".to_string(),
                "Use evaluator metrics to focus on the dominant bottleneck.".to_string(),
                "Prefer robust implementations that preserve correctness.".to_string(),
                "Leverage successful inspirations, then adapt to local constraints.".to_string(),
            ]
        });

        let n = candidates.len().max(1);
        Self {
            enabled,
            num_fewshot_traces,
            max_traces: max_traces.max(1),
            min_improvement,
            exploration_weight,
            candidate_instructions: candidates,
            total_trials: 0,
            candidate_trials: vec![0; n],
            candidate_total_delta: vec![0.0; n],
            traces: Vec::new(),
        }
    }

    pub fn build_prompt_context(&self) -> GepaPromptContext {
        if !self.enabled {
            return GepaPromptContext::default();
        }
        let candidate_id = self.select_candidate();
        let candidate_instruction = Some(self.candidate_instructions[candidate_id].clone());
        let fewshot_examples = self.format_fewshot_examples();
        GepaPromptContext {
            candidate_id: Some(candidate_id),
            candidate_instruction,
            fewshot_examples,
        }
    }

    #[allow(clippy::too_many_arguments)]
    pub fn observe_result(
        &mut self,
        generation: usize,
        parent_score: f64,
        child_score: f64,
        patch_type: &str,
        patch_name: &str,
        patch_description: &str,
        diff_summary: &str,
        candidate_id: Option<usize>,
        correct: bool,
    ) {
        if !self.enabled {
            return;
        }

        let delta = child_score - parent_score;
        if let Some(idx) = candidate_id {
            if idx < self.candidate_trials.len() {
                self.total_trials += 1;
                self.candidate_trials[idx] += 1;
                self.candidate_total_delta[idx] += delta;
            }
        }

        if !correct || delta < self.min_improvement {
            return;
        }

        let instruction =
            candidate_id.and_then(|idx| self.candidate_instructions.get(idx).cloned());
        self.traces.push(GepaTrace {
            generation,
            parent_score,
            child_score,
            score_delta: delta,
            patch_type: patch_type.to_string(),
            patch_name: patch_name.to_string(),
            patch_description: patch_description.to_string(),
            diff_summary: diff_summary.to_string(),
            candidate_id,
            candidate_instruction: instruction,
        });

        self.traces
            .sort_by(|a, b| b.score_delta.total_cmp(&a.score_delta));
        if self.traces.len() > self.max_traces {
            self.traces.truncate(self.max_traces);
        }
    }

    pub fn save_state(&self, path: &str) -> anyhow::Result<()> {
        if !self.enabled {
            return Ok(());
        }
        std::fs::write(path, serde_json::to_string_pretty(self)?)?;
        Ok(())
    }

    pub fn load_state(&mut self, path: &str) -> bool {
        if !self.enabled {
            return false;
        }
        let Ok(raw) = std::fs::read_to_string(path) else {
            return false;
        };
        let Ok(parsed) = serde_json::from_str::<GepaStyleOptimizer>(&raw) else {
            return false;
        };
        *self = parsed;
        true
    }

    fn select_candidate(&self) -> usize {
        for (idx, trials) in self.candidate_trials.iter().enumerate() {
            if *trials == 0 {
                return idx;
            }
        }

        let mut best_idx = 0usize;
        let mut best_score = f64::NEG_INFINITY;
        for idx in 0..self.candidate_instructions.len() {
            let trials = self.candidate_trials[idx] as f64;
            let total_delta = self.candidate_total_delta[idx];
            let avg_delta = total_delta / trials.max(1.0);
            let ucb = self.exploration_weight
                * (((self.total_trials.max(1) as f64).ln() + 1.0) / trials.max(1.0)).sqrt();
            let score = avg_delta + ucb;
            if score > best_score {
                best_score = score;
                best_idx = idx;
            }
        }
        best_idx
    }

    fn format_fewshot_examples(&self) -> Option<String> {
        if self.num_fewshot_traces == 0 || self.traces.is_empty() {
            return None;
        }
        let mut lines = Vec::new();
        for (idx, t) in self.traces.iter().take(self.num_fewshot_traces).enumerate() {
            lines.push(format!("## Successful Trace {}", idx + 1));
            lines.push(format!("- Generation: {}", t.generation));
            lines.push(format!("- Score delta: {:+.4}", t.score_delta));
            lines.push(format!("- Mutation type: {}", t.patch_type));
            if !t.patch_name.is_empty() {
                lines.push(format!("- Mutation name: {}", t.patch_name));
            }
            if !t.patch_description.is_empty() {
                lines.push(format!("- Why it helped: {}", t.patch_description));
            }
            if !t.diff_summary.is_empty() {
                lines.push(format!("- Key edit summary: {}", t.diff_summary));
            }
            if let Some(instr) = &t.candidate_instruction {
                lines.push(format!("- Guidance used: {}", instr));
            }
            lines.push(String::new());
        }
        Some(lines.join("\n"))
    }
}

#[derive(Debug, Clone, Default)]
pub struct GepaPromptContext {
    pub candidate_id: Option<usize>,
    pub candidate_instruction: Option<String>,
    pub fewshot_examples: Option<String>,
}
