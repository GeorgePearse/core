use anyhow::{Context, Result};
use std::process::Command;

use crate::config::EvolutionConfig;

#[derive(Debug, Clone, Default)]
pub struct EvalResult {
    pub correct: bool,
    pub combined_score: f64,
    pub text_feedback: String,
}

pub trait JobScheduler {
    fn run(&self, code: &str, generation: usize) -> Result<EvalResult>;
}

pub fn build_scheduler(cfg: &EvolutionConfig) -> Box<dyn JobScheduler> {
    match cfg.scheduler_backend.as_str() {
        "local_command" => Box::new(LocalCommandScheduler {
            eval_command: cfg.eval_command.clone(),
            language: cfg.language.clone(),
        }),
        _ => Box::new(MockScheduler),
    }
}

#[derive(Debug, Clone, Default)]
pub struct MockScheduler;

impl JobScheduler for MockScheduler {
    fn run(&self, code: &str, generation: usize) -> Result<EvalResult> {
        let score = (code.len() as f64 % 1000.0) / 1000.0 + generation as f64 * 0.001;
        Ok(EvalResult {
            correct: true,
            combined_score: score,
            text_feedback: "mock evaluator feedback".to_string(),
        })
    }
}

#[derive(Debug, Clone)]
pub struct LocalCommandScheduler {
    pub eval_command: Option<String>,
    pub language: String,
}

impl JobScheduler for LocalCommandScheduler {
    fn run(&self, code: &str, generation: usize) -> Result<EvalResult> {
        let Some(cmd) = &self.eval_command else {
            return Ok(EvalResult {
                correct: true,
                combined_score: 0.0,
                text_feedback: "eval_command not set".to_string(),
            });
        };

        let ext = match self.language.as_str() {
            "rust" => "rs",
            "cpp" => "cpp",
            "cuda" => "cu",
            _ => "py",
        };

        let temp_dir = tempfile::tempdir().with_context(|| "failed to create temp dir")?;
        let code_path = temp_dir.path().join(format!("main.{}", ext));
        std::fs::write(&code_path, code).with_context(|| "failed writing temp code file")?;

        let output = Command::new("sh")
            .arg("-lc")
            .arg(cmd)
            .env("GENESIS_CODE_PATH", &code_path)
            .env("GENESIS_GENERATION", generation.to_string())
            .output()
            .with_context(|| "failed to execute eval command")?;

        let stdout = String::from_utf8_lossy(&output.stdout).to_string();
        let stderr = String::from_utf8_lossy(&output.stderr).to_string();

        if let Ok(json) = serde_json::from_str::<serde_json::Value>(&stdout) {
            let correct = json
                .get("correct")
                .and_then(|v| v.as_bool())
                .unwrap_or(output.status.success());
            let combined_score = json
                .get("combined_score")
                .and_then(|v| v.as_f64())
                .unwrap_or(0.0);
            let text_feedback = json
                .get("text_feedback")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string();
            return Ok(EvalResult {
                correct,
                combined_score,
                text_feedback,
            });
        }

        Ok(EvalResult {
            correct: output.status.success(),
            combined_score: if output.status.success() { 1.0 } else { 0.0 },
            text_feedback: if stderr.is_empty() { stdout } else { stderr },
        })
    }
}
