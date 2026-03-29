use crate::types::Program;

#[derive(Debug, Clone, Default)]
pub struct MetaSummarizer {
    pub meta_summary: Option<String>,
    pub meta_recommendations: Option<String>,
    pub evaluated_since_last_meta: Vec<Program>,
}

impl MetaSummarizer {
    pub fn add_evaluated_program(&mut self, p: Program) {
        self.evaluated_since_last_meta.push(p);
    }

    pub fn should_update_meta(&self, meta_rec_interval: Option<usize>) -> bool {
        if let Some(interval) = meta_rec_interval {
            self.evaluated_since_last_meta.len() >= interval
        } else {
            false
        }
    }

    pub fn update_meta_memory(&mut self) -> Option<String> {
        if self.evaluated_since_last_meta.is_empty() {
            return None;
        }
        let best = self
            .evaluated_since_last_meta
            .iter()
            .max_by(|a, b| a.combined_score.total_cmp(&b.combined_score))?;

        let rec = format!(
            "Prefer mutation patterns similar to generation {} with score {:.4}",
            best.generation, best.combined_score
        );
        self.meta_summary = Some(rec.clone());
        self.meta_recommendations = Some(rec.clone());
        self.evaluated_since_last_meta.clear();
        Some(rec)
    }

    pub fn get_current(&self) -> Option<String> {
        self.meta_recommendations.clone()
    }
}
