use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use uuid::Uuid;

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct Program {
    pub id: Uuid,
    pub code: String,
    pub language: String,
    pub parent_id: Option<Uuid>,
    pub generation: i32,
    pub combined_score: f64,
    pub correct: bool,
    pub public_metrics: HashMap<String, serde_json::Value>,
    pub private_metrics: HashMap<String, serde_json::Value>,
    pub text_feedback: String,
    pub metadata: HashMap<String, serde_json::Value>,
    pub timestamp: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct RunningJob {
    pub job_id: String,
    pub generation: i32,
    pub parent_id: Option<Uuid>,
    pub patch_type: String,
    pub patch_name: Option<String>,
    pub patch_description: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct PatchRequest {
    pub parent: Program,
    pub archive_inspirations: Vec<Program>,
    pub top_k_inspirations: Vec<Program>,
    pub meta_recommendations: Option<String>,
    pub alma_memory_context: Option<String>,
    pub gepa_instruction: Option<String>,
    pub gepa_fewshot_examples: Option<String>,
}
