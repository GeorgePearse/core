#![allow(clippy::too_many_arguments)]

use anyhow::{Context, Result};
use chrono::{DateTime, Utc};
use serde_json::Value as JsonValue;
use sqlx::postgres::PgPoolOptions;
use sqlx::PgPool;
use uuid::Uuid;

#[derive(Clone)]
pub struct PgProgramDatabase {
    pool: PgPool,
}

impl PgProgramDatabase {
    pub async fn new(database_url: &str) -> Result<Self> {
        let pool = PgPoolOptions::new()
            .max_connections(5)
            .connect(database_url)
            .await
            .with_context(|| "failed to connect to postgres")?;
        Ok(Self { pool })
    }

    pub fn from_pool(pool: PgPool) -> Self {
        Self { pool }
    }

    pub fn pool(&self) -> &PgPool {
        &self.pool
    }

    // -- evolution_runs --

    pub async fn create_evolution_run(
        &self,
        task_name: &str,
        config: &JsonValue,
        population_size: i32,
        cluster_type: Option<&str>,
        database_path: Option<&str>,
    ) -> Result<Uuid> {
        let row = sqlx::query_scalar::<_, Uuid>(
            r#"INSERT INTO evolution_runs (task_name, config, population_size, cluster_type, database_path)
               VALUES ($1, $2, $3, $4, $5)
               RETURNING run_id"#,
        )
        .bind(task_name)
        .bind(config)
        .bind(population_size)
        .bind(cluster_type)
        .bind(database_path)
        .fetch_one(&self.pool)
        .await
        .with_context(|| "failed to insert evolution_run")?;

        Ok(row)
    }

    pub async fn update_evolution_run_status(
        &self,
        run_id: Uuid,
        status: &str,
        total_generations: i32,
    ) -> Result<()> {
        sqlx::query(
            r#"UPDATE evolution_runs
               SET status = $1, total_generations = $2, end_time = now()
               WHERE run_id = $3"#,
        )
        .bind(status)
        .bind(total_generations)
        .bind(run_id)
        .execute(&self.pool)
        .await
        .with_context(|| "failed to update evolution_run")?;

        Ok(())
    }

    // -- generations --

    pub async fn log_generation(
        &self,
        run_id: Uuid,
        generation: i32,
        num_individuals: i32,
        best_score: f64,
        avg_score: f64,
        pareto_size: i32,
        total_cost: f64,
        metadata: &JsonValue,
    ) -> Result<()> {
        sqlx::query(
            r#"INSERT INTO generations (run_id, generation, num_individuals, best_score, avg_score, pareto_size, total_cost, metadata)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8)"#,
        )
        .bind(run_id)
        .bind(generation)
        .bind(num_individuals)
        .bind(best_score)
        .bind(avg_score)
        .bind(pareto_size)
        .bind(total_cost)
        .bind(metadata)
        .execute(&self.pool)
        .await
        .with_context(|| "failed to insert generation")?;

        Ok(())
    }

    // -- individuals --

    pub async fn add_individual(
        &self,
        run_id: Uuid,
        individual_id: Uuid,
        generation: i32,
        parent_id: Option<Uuid>,
        mutation_type: &str,
        fitness_score: f64,
        combined_score: f64,
        metrics: &JsonValue,
        is_pareto: bool,
        correct: bool,
        api_cost: f64,
        embed_cost: f64,
        novelty_cost: f64,
        code_hash: &str,
        code_size: i32,
        code: &str,
        language: &str,
        text_feedback: &str,
    ) -> Result<()> {
        sqlx::query(
            r#"INSERT INTO individuals
               (run_id, individual_id, generation, parent_id, mutation_type,
                fitness_score, combined_score, metrics, is_pareto, correct,
                api_cost, embed_cost, novelty_cost, code_hash, code_size,
                code, language, text_feedback)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18)"#,
        )
        .bind(run_id)
        .bind(individual_id)
        .bind(generation)
        .bind(parent_id)
        .bind(mutation_type)
        .bind(fitness_score)
        .bind(combined_score)
        .bind(metrics)
        .bind(is_pareto)
        .bind(correct)
        .bind(api_cost)
        .bind(embed_cost)
        .bind(novelty_cost)
        .bind(code_hash)
        .bind(code_size)
        .bind(code)
        .bind(language)
        .bind(text_feedback)
        .execute(&self.pool)
        .await
        .with_context(|| "failed to insert individual")?;

        Ok(())
    }

    pub async fn get_best_individual(&self, run_id: Uuid) -> Result<Option<IndividualRow>> {
        let row = sqlx::query_as::<_, IndividualRow>(
            r#"SELECT run_id, individual_id, generation, timestamp, parent_id,
                      mutation_type, fitness_score, combined_score, metrics,
                      is_pareto, api_cost, embed_cost, novelty_cost, code_hash, code_size
               FROM individuals
               WHERE run_id = $1
               ORDER BY combined_score DESC
               LIMIT 1"#,
        )
        .bind(run_id)
        .fetch_optional(&self.pool)
        .await
        .with_context(|| "failed to fetch best individual")?;

        Ok(row)
    }

    pub async fn get_top_individuals(&self, run_id: Uuid, n: i64) -> Result<Vec<IndividualRow>> {
        let rows = sqlx::query_as::<_, IndividualRow>(
            r#"SELECT run_id, individual_id, generation, timestamp, parent_id,
                      mutation_type, fitness_score, combined_score, metrics,
                      is_pareto, api_cost, embed_cost, novelty_cost, code_hash, code_size
               FROM individuals
               WHERE run_id = $1
               ORDER BY combined_score DESC
               LIMIT $2"#,
        )
        .bind(run_id)
        .bind(n)
        .fetch_all(&self.pool)
        .await
        .with_context(|| "failed to fetch top individuals")?;

        Ok(rows)
    }

    // -- pareto_fronts --

    pub async fn log_pareto_front(
        &self,
        run_id: Uuid,
        generation: i32,
        individual_id: Uuid,
        fitness_score: f64,
        combined_score: f64,
        metrics: &JsonValue,
    ) -> Result<()> {
        sqlx::query(
            r#"INSERT INTO pareto_fronts (run_id, generation, individual_id, fitness_score, combined_score, metrics)
               VALUES ($1, $2, $3, $4, $5, $6)"#,
        )
        .bind(run_id)
        .bind(generation)
        .bind(individual_id)
        .bind(fitness_score)
        .bind(combined_score)
        .bind(metrics)
        .execute(&self.pool)
        .await
        .with_context(|| "failed to insert pareto_front")?;

        Ok(())
    }

    // -- code_lineages --

    pub async fn log_lineage(
        &self,
        run_id: Uuid,
        child_id: Uuid,
        parent_id: Option<Uuid>,
        generation: i32,
        mutation_type: &str,
        fitness_delta: f64,
        edit_summary: &str,
    ) -> Result<()> {
        sqlx::query(
            r#"INSERT INTO code_lineages (run_id, child_id, parent_id, generation, mutation_type, fitness_delta, edit_summary)
               VALUES ($1, $2, $3, $4, $5, $6, $7)"#,
        )
        .bind(run_id)
        .bind(child_id)
        .bind(parent_id)
        .bind(generation)
        .bind(mutation_type)
        .bind(fitness_delta)
        .bind(edit_summary)
        .execute(&self.pool)
        .await
        .with_context(|| "failed to insert code_lineage")?;

        Ok(())
    }

    // -- llm_logs --

    pub async fn log_llm_interaction(
        &self,
        model: &str,
        messages: &JsonValue,
        response: &str,
        thought: &str,
        cost: f64,
        execution_time: f64,
        metadata: &JsonValue,
    ) -> Result<()> {
        sqlx::query(
            r#"INSERT INTO llm_logs (model, messages, response, thought, cost, execution_time, metadata)
               VALUES ($1, $2, $3, $4, $5, $6, $7)"#,
        )
        .bind(model)
        .bind(messages)
        .bind(response)
        .bind(thought)
        .bind(cost)
        .bind(execution_time)
        .bind(metadata)
        .execute(&self.pool)
        .await
        .with_context(|| "failed to insert llm_log")?;

        Ok(())
    }

    // -- agent_actions --

    pub async fn log_agent_action(
        &self,
        action_type: &str,
        details: &JsonValue,
        metadata: &JsonValue,
    ) -> Result<()> {
        sqlx::query(
            r#"INSERT INTO agent_actions (action_type, details, metadata)
               VALUES ($1, $2, $3)"#,
        )
        .bind(action_type)
        .bind(details)
        .bind(metadata)
        .execute(&self.pool)
        .await
        .with_context(|| "failed to insert agent_action")?;

        Ok(())
    }
}

#[derive(Debug, Clone, sqlx::FromRow)]
pub struct IndividualRow {
    pub run_id: Uuid,
    pub individual_id: Uuid,
    pub generation: i32,
    pub timestamp: DateTime<Utc>,
    pub parent_id: Option<Uuid>,
    pub mutation_type: String,
    pub fitness_score: f64,
    pub combined_score: f64,
    pub metrics: JsonValue,
    pub is_pareto: bool,
    pub api_cost: f64,
    pub embed_cost: f64,
    pub novelty_cost: f64,
    pub code_hash: String,
    pub code_size: i32,
}
