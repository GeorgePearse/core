use anyhow::Result;
use chrono::Utc;
use std::collections::HashMap;
use uuid::Uuid;

use crate::config::EvolutionConfig;
use crate::core::alma_memory::AlmaMemorySystem;
use crate::core::gepa_optimizer::GepaStyleOptimizer;
use crate::core::novelty_judge::NoveltyJudge;
use crate::core::sampler::PromptSampler;
use crate::core::summarizer::MetaSummarizer;
use crate::database::PgProgramDatabase;
use crate::launch::{build_scheduler, JobScheduler};
use crate::llm::{build_llm_client, LlmClientDyn};
use crate::types::{PatchRequest, Program};

pub struct EvolutionRunner {
    pub cfg: EvolutionConfig,
    pub db: Option<PgProgramDatabase>,
    pub llm: Box<dyn LlmClientDyn>,
    pub scheduler: Box<dyn JobScheduler>,
    pub prompt_sampler: PromptSampler,
    pub meta_summarizer: MetaSummarizer,
    pub novelty_judge: NoveltyJudge,
    pub alma_memory: AlmaMemorySystem,
    pub gepa_optimizer: GepaStyleOptimizer,
    pub run_id: Option<Uuid>,
    programs: Vec<Program>,
}

impl EvolutionRunner {
    pub fn new(cfg: EvolutionConfig) -> Self {
        let prompt_sampler = PromptSampler::new(
            cfg.task_sys_msg.clone(),
            cfg.language.clone(),
            cfg.patch_types.clone(),
            cfg.patch_type_probs.clone(),
            cfg.use_text_feedback,
        );

        let llm = build_llm_client(&cfg).unwrap_or_else(|_| {
            build_llm_client(&EvolutionConfig::default()).expect("default llm")
        });
        let scheduler = build_scheduler(&cfg);

        Self {
            novelty_judge: NoveltyJudge::new(1.0),
            alma_memory: AlmaMemorySystem::new(
                cfg.alma_enabled,
                cfg.alma_max_entries,
                cfg.alma_max_retrievals,
                cfg.alma_min_success_delta,
            ),
            gepa_optimizer: GepaStyleOptimizer::new(
                cfg.gepa_enabled,
                cfg.gepa_num_fewshot_traces,
                cfg.gepa_max_traces,
                cfg.gepa_min_improvement,
                cfg.gepa_exploration_weight,
                cfg.gepa_candidate_instructions.clone(),
            ),
            cfg,
            db: None,
            llm,
            scheduler,
            prompt_sampler,
            meta_summarizer: MetaSummarizer::default(),
            run_id: None,
            programs: Vec::new(),
        }
    }

    pub async fn init_db(&mut self) -> Result<()> {
        if let Some(url) = &self.cfg.database_url {
            let db = PgProgramDatabase::new(url).await?;
            self.db = Some(db);
        }
        Ok(())
    }

    pub async fn run(&mut self) -> Result<()> {
        if let Some(db) = &self.db {
            let run_id = db
                .create_evolution_run(
                    self.cfg.task_sys_msg.as_deref().unwrap_or("unknown"),
                    &serde_json::json!({}),
                    self.cfg.num_generations as i32,
                    None,
                    None,
                )
                .await?;
            self.run_id = Some(run_id);
        }

        self.run_generation_0().await?;

        for generation in 1..self.cfg.num_generations {
            self.run_generation(generation).await?;
        }

        if let (Some(db), Some(run_id)) = (&self.db, self.run_id) {
            db.update_evolution_run_status(run_id, "completed", self.cfg.num_generations as i32)
                .await?;
        }

        self.save_state()?;
        if let Some(best) = self.get_best_program() {
            println!(
                "[genesis] best program gen={} score={:.4}",
                best.generation, best.combined_score
            );
        }
        Ok(())
    }

    async fn run_generation_0(&mut self) -> Result<()> {
        let code = if let Some(path) = &self.cfg.init_program_path {
            std::fs::read_to_string(path)?
        } else {
            let (sys, user) = self.prompt_sampler.initial_program_prompt();
            let resp = self.llm.query_dyn(&user, &sys).await?;
            resp.content
        };
        let eval = self.scheduler.run(&code, 0)?;

        let program = Program {
            id: Uuid::new_v4(),
            code,
            language: self.cfg.language.clone(),
            parent_id: None,
            generation: 0,
            combined_score: eval.combined_score,
            correct: eval.correct,
            public_metrics: HashMap::new(),
            private_metrics: HashMap::new(),
            text_feedback: eval.text_feedback,
            metadata: HashMap::new(),
            timestamp: Utc::now(),
        };

        if let (Some(db), Some(run_id)) = (&self.db, self.run_id) {
            db.add_individual(
                run_id,
                program.id,
                program.generation,
                program.parent_id,
                "init",
                program.combined_score,
                program.combined_score,
                &serde_json::json!({}),
                false,
                0.0,
                0.0,
                0.0,
                "",
                program.code.len() as i32,
                &program.code,
                &program.language,
                &program.text_feedback,
            )
            .await?;
        }

        self.meta_summarizer.add_evaluated_program(program.clone());
        self.programs.push(program);
        Ok(())
    }

    async fn run_generation(&mut self, generation: usize) -> Result<()> {
        let parent = self
            .get_best_program()
            .ok_or_else(|| anyhow::anyhow!("no parent available for generation {generation}"))?;

        let meta_recommendations = if self
            .meta_summarizer
            .should_update_meta(Some(self.cfg.max_parallel_jobs.max(1)))
        {
            self.meta_summarizer.update_meta_memory()
        } else {
            self.meta_summarizer.get_current()
        };

        let alma_context =
            self.alma_memory
                .build_prompt_context(generation, &parent.code, &parent.text_feedback);
        let gepa_ctx = self.gepa_optimizer.build_prompt_context();

        let top_k: Vec<Program> = {
            let mut sorted = self.programs.clone();
            sorted.sort_by(|a, b| b.combined_score.total_cmp(&a.combined_score));
            sorted
                .into_iter()
                .take(6)
                .filter(|p| p.id != parent.id)
                .collect()
        };
        let archive = top_k.iter().take(4).cloned().collect();

        let req = PatchRequest {
            parent: parent.clone(),
            archive_inspirations: archive,
            top_k_inspirations: top_k.into_iter().take(2).collect(),
            meta_recommendations,
            alma_memory_context: alma_context,
            gepa_instruction: gepa_ctx.candidate_instruction.clone(),
            gepa_fewshot_examples: gepa_ctx.fewshot_examples.clone(),
        };

        let (patch_sys, patch_msg, patch_type) = self.prompt_sampler.sample(&req);
        let resp = self.llm.query_dyn(&patch_msg, &patch_sys).await?;
        let eval = self.scheduler.run(&resp.content, generation)?;

        if !self.novelty_judge.should_accept(0.0) {
            return Ok(());
        }

        let mut metadata = HashMap::new();
        metadata.insert(
            "patch_type".to_string(),
            serde_json::Value::String(patch_type.clone()),
        );
        if let Some(idx) = gepa_ctx.candidate_id {
            metadata.insert(
                "gepa_candidate_id".to_string(),
                serde_json::Value::Number(idx.into()),
            );
        }

        let program = Program {
            id: Uuid::new_v4(),
            code: resp.content,
            language: self.cfg.language.clone(),
            parent_id: Some(parent.id),
            generation: generation as i32,
            combined_score: eval.combined_score,
            correct: eval.correct,
            public_metrics: HashMap::new(),
            private_metrics: HashMap::new(),
            text_feedback: eval.text_feedback.clone(),
            metadata,
            timestamp: Utc::now(),
        };

        if let (Some(db), Some(run_id)) = (&self.db, self.run_id) {
            db.add_individual(
                run_id,
                program.id,
                program.generation,
                program.parent_id,
                &patch_type,
                program.combined_score,
                program.combined_score,
                &serde_json::json!({}),
                false,
                0.0,
                0.0,
                0.0,
                "",
                program.code.len() as i32,
                &program.code,
                &program.language,
                &program.text_feedback,
            )
            .await?;

            let delta = program.combined_score - parent.combined_score;
            db.log_lineage(
                run_id,
                program.id,
                Some(parent.id),
                program.generation,
                &patch_type,
                delta,
                "",
            )
            .await?;
        }

        self.meta_summarizer.add_evaluated_program(program.clone());

        let delta = program.combined_score - parent.combined_score;
        self.gepa_optimizer.observe_result(
            generation,
            parent.combined_score,
            program.combined_score,
            &patch_type,
            "genesis-patch",
            "Generated mutation",
            "diff summary unavailable",
            gepa_ctx.candidate_id,
            program.correct,
        );
        self.alma_memory.observe_outcome(
            generation,
            parent.combined_score,
            program.combined_score,
            program.correct,
            &patch_type,
            "genesis-patch",
            "Generated mutation",
            "diff summary unavailable",
            &program.text_feedback,
            "",
        );

        println!(
            "[genesis] gen={} parent={:.4} child={:.4} delta={:+.4}",
            generation, parent.combined_score, program.combined_score, delta
        );

        self.programs.push(program);
        self.save_state()?;
        Ok(())
    }

    fn get_best_program(&self) -> Option<Program> {
        self.programs
            .iter()
            .filter(|p| p.correct)
            .max_by(|a, b| a.combined_score.total_cmp(&b.combined_score))
            .cloned()
            .or_else(|| self.programs.last().cloned())
    }

    fn save_state(&self) -> Result<()> {
        self.alma_memory.save_state("alma_memory.json")?;
        self.gepa_optimizer.save_state("gepa_state.json")?;
        Ok(())
    }

    pub fn restore_state(&mut self) {
        let _ = self.alma_memory.load_state("alma_memory.json");
        let _ = self.gepa_optimizer.load_state("gepa_state.json");
    }
}
