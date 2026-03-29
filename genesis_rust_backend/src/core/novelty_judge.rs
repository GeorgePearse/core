#[derive(Debug, Clone)]
pub struct NoveltyJudge {
    pub similarity_threshold: f64,
}

impl NoveltyJudge {
    pub fn new(similarity_threshold: f64) -> Self {
        Self {
            similarity_threshold,
        }
    }

    pub fn should_accept(&self, similarity: f64) -> bool {
        similarity <= self.similarity_threshold
    }
}
