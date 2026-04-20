use rand::distributions::WeightedIndex;
use rand::prelude::*;

use crate::types::{PatchRequest, Program};

#[derive(Debug, Clone)]
pub struct PromptSampler {
    pub task_sys_msg: Option<String>,
    pub language: String,
    pub patch_types: Vec<String>,
    pub patch_type_probs: Vec<f64>,
    pub use_text_feedback: bool,
}

impl PromptSampler {
    pub fn new(
        task_sys_msg: Option<String>,
        language: String,
        patch_types: Vec<String>,
        patch_type_probs: Vec<f64>,
        use_text_feedback: bool,
    ) -> Self {
        Self {
            task_sys_msg,
            language,
            patch_types,
            patch_type_probs,
            use_text_feedback,
        }
    }

    pub fn initial_program_prompt(&self) -> (String, String) {
        let sys_msg = self
            .task_sys_msg
            .clone()
            .unwrap_or_else(|| "You are an expert code optimizer.".to_string());
        let user_msg = format!(
            "Write an initial {} program enclosed in fenced code blocks.",
            self.language
        );
        (sys_msg, user_msg)
    }

    pub fn sample(&self, req: &PatchRequest) -> (String, String, String) {
        let mut sys_msg = self
            .task_sys_msg
            .clone()
            .unwrap_or_else(|| "You are an expert code optimizer.".to_string());

        if let Some(gepa_instruction) = &req.gepa_instruction {
            if !gepa_instruction.is_empty() {
                sys_msg.push_str("\n\n# GEPA Optimization Guidance\n");
                sys_msg.push_str(gepa_instruction);
            }
        }

        let patch_type = self.sample_patch_type(&req.archive_inspirations, &req.top_k_inspirations);

        let mut history = String::new();
        append_program_list(
            &mut history,
            "Archive Inspirations",
            &req.archive_inspirations,
        );
        append_program_list(&mut history, "Top-K Inspirations", &req.top_k_inspirations);

        if let Some(alma_memory_context) = &req.alma_memory_context {
            if !alma_memory_context.is_empty() {
                history.push_str("\n\n");
                history.push_str(alma_memory_context);
            }
        }

        if let Some(gepa_fewshot_examples) = &req.gepa_fewshot_examples {
            if !gepa_fewshot_examples.is_empty() {
                history.push_str("\n\n# GEPA Bootstrapped Mutation Traces\n");
                history.push_str(gepa_fewshot_examples);
            }
        }

        if let Some(meta) = &req.meta_recommendations {
            if !meta.is_empty() && patch_type != "cross" {
                sys_msg.push_str("\n\n# Potential Recommendations\n");
                sys_msg.push_str(meta);
            }
        }

        let iter_msg = self.build_iter_msg(&req.parent, &patch_type);
        let user_msg = if history.is_empty() {
            iter_msg
        } else {
            format!("{}\n\n{}", history, iter_msg)
        };

        (sys_msg, user_msg, patch_type)
    }

    fn sample_patch_type(&self, archive: &[Program], top_k: &[Program]) -> String {
        let mut patch_types = self.patch_types.clone();
        let mut patch_probs = self.patch_type_probs.clone();

        if archive.is_empty() && top_k.is_empty() {
            let mut filtered = Vec::new();
            let mut filtered_probs = Vec::new();
            for (t, p) in patch_types.iter().zip(patch_probs.iter()) {
                if t != "cross" {
                    filtered.push(t.clone());
                    filtered_probs.push(*p);
                }
            }
            if !filtered.is_empty() {
                patch_types = filtered;
                patch_probs = filtered_probs;
            }
        }

        if patch_types.is_empty() {
            return "diff".to_string();
        }

        let dist = WeightedIndex::new(&patch_probs).ok();
        let mut rng = thread_rng();
        if let Some(d) = dist {
            patch_types[d.sample(&mut rng)].clone()
        } else {
            patch_types[0].clone()
        }
    }

    fn build_iter_msg(&self, parent: &Program, patch_type: &str) -> String {
        let mut msg = format!(
            "# Task\nImprove this {} program. Current score: {:.4}.\n\n# Code\n```{}\n{}\n```",
            self.language, parent.combined_score, self.language, parent.code
        );

        if self.use_text_feedback && !parent.text_feedback.is_empty() {
            msg.push_str("\n\n# Evaluator Feedback\n");
            msg.push_str(&parent.text_feedback);
        }

        msg.push_str("\n\n# Required Output\n");
        if patch_type == "full" {
            msg.push_str(
                "Return ONLY the complete improved program inside a single fenced code block.\n\
                 Do NOT include any text before or after the code block.\n\
                 The code must include ALL functions from the original program.",
            );
        } else {
            msg.push_str("Return <NAME>, <DESCRIPTION>, and patch content.");
            msg.push_str(&format!("\nPatch mode: {patch_type}"));
        }
        msg
    }
}

fn append_program_list(dst: &mut String, title: &str, programs: &[Program]) {
    if programs.is_empty() {
        return;
    }
    dst.push_str(&format!("# {title}\n"));
    for p in programs {
        dst.push_str(&format!(
            "- Gen {} | Score {:.4} | Correct {} | id={}\n",
            p.generation, p.combined_score, p.correct, p.id
        ));
    }
}
