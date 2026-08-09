use std::net::SocketAddr;
use std::sync::Arc;

use anyhow::Result;
use axum::{
    extract::{Path, State},
    http::StatusCode,
    routing::get,
    Json, Router,
};
use serde_json::json;
use tower_http::cors::CorsLayer;
use tower_http::trace::TraceLayer;
use tracing_subscriber::EnvFilter;

use genesis_rust_backend::config::EvolutionConfig;
use genesis_rust_backend::core::runner::EvolutionRunner;
use genesis_rust_backend::database::PgProgramDatabase;

struct AppState {
    db: PgProgramDatabase,
    #[allow(dead_code)]
    config: EvolutionConfig,
}

#[tokio::main]
async fn main() -> Result<()> {
    dotenvy::dotenv().ok();

    tracing_subscriber::fmt()
        .with_env_filter(EnvFilter::from_default_env())
        .init();

    let args: Vec<String> = std::env::args().collect();
    let run_mode = args.iter().any(|a| a == "--run");

    let cfg = if let Some(idx) = args.iter().position(|a| a == "--config") {
        if let Some(path) = args.get(idx + 1) {
            EvolutionConfig::from_yaml_file(path)?
        } else {
            EvolutionConfig::default()
        }
    } else {
        EvolutionConfig::default()
    };

    if run_mode {
        tracing::info!("starting evolution run");
        let mut runner = EvolutionRunner::new(cfg);
        runner.init_db().await?;
        runner.run().await?;
        tracing::info!("evolution run complete");
        return Ok(());
    }

    let database_url = cfg
        .database_url
        .as_deref()
        .unwrap_or("postgresql://localhost:5432/genesis");

    let db = PgProgramDatabase::new(database_url).await?;
    tracing::info!("connected to postgres");

    let state = Arc::new(AppState {
        db,
        config: cfg.clone(),
    });

    let app = Router::new()
        .route("/health", get(health))
        .route("/api/runs", get(list_runs))
        .route("/api/runs/{run_id}", get(get_run))
        .route("/api/runs/{run_id}/individuals", get(list_individuals))
        .route("/api/runs/{run_id}/generations", get(list_generations))
        .route(
            "/api/runs/{run_id}/generations/{generation}",
            get(get_generation),
        )
        .route("/api/runs/{run_id}/lineage", get(get_lineage))
        .layer(CorsLayer::permissive())
        .layer(TraceLayer::new_for_http())
        .with_state(state);

    let addr = SocketAddr::from(([0, 0, 0, 0], cfg.server_port));
    tracing::info!("listening on {}", addr);

    let listener = tokio::net::TcpListener::bind(addr).await?;
    axum::serve(listener, app).await?;

    Ok(())
}

async fn health() -> (StatusCode, Json<serde_json::Value>) {
    (StatusCode::OK, Json(json!({"status": "ok"})))
}

// --- Runs ---

async fn list_runs(
    State(state): State<Arc<AppState>>,
) -> Result<Json<serde_json::Value>, StatusCode> {
    let rows = sqlx::query_as::<_, EvolutionRunRow>(
        r#"SELECT run_id, start_time, end_time, task_name, status,
                  total_generations, population_size, config
           FROM evolution_runs
           ORDER BY start_time DESC
           LIMIT 50"#,
    )
    .fetch_all(state.db.pool())
    .await
    .map_err(|e| {
        tracing::error!("failed to list runs: {e}");
        StatusCode::INTERNAL_SERVER_ERROR
    })?;

    let runs: Vec<serde_json::Value> = rows.into_iter().map(|r| run_to_json(&r)).collect();
    Ok(Json(json!({"runs": runs})))
}

async fn get_run(
    State(state): State<Arc<AppState>>,
    Path(run_id): Path<uuid::Uuid>,
) -> Result<Json<serde_json::Value>, StatusCode> {
    let row = sqlx::query_as::<_, EvolutionRunRow>(
        r#"SELECT run_id, start_time, end_time, task_name, status,
                  total_generations, population_size, config
           FROM evolution_runs
           WHERE run_id = $1"#,
    )
    .bind(run_id)
    .fetch_optional(state.db.pool())
    .await
    .map_err(|e| {
        tracing::error!("failed to get run: {e}");
        StatusCode::INTERNAL_SERVER_ERROR
    })?
    .ok_or(StatusCode::NOT_FOUND)?;

    Ok(Json(run_to_json(&row)))
}

fn run_to_json(r: &EvolutionRunRow) -> serde_json::Value {
    json!({
        "run_id": r.run_id,
        "start_time": r.start_time,
        "end_time": r.end_time,
        "task_name": r.task_name,
        "status": r.status,
        "total_generations": r.total_generations,
        "population_size": r.population_size,
        "config": r.config,
    })
}

// --- Individuals ---

async fn list_individuals(
    State(state): State<Arc<AppState>>,
    Path(run_id): Path<uuid::Uuid>,
) -> Result<Json<serde_json::Value>, StatusCode> {
    let rows = sqlx::query_as::<_, IndividualApiRow>(
        r#"SELECT i.run_id, i.individual_id, i.generation, i.timestamp,
                  i.parent_id, i.mutation_type, i.fitness_score,
                  i.combined_score, i.metrics, i.is_pareto,
                  i.correct,
                  i.api_cost, i.embed_cost, i.novelty_cost,
                  i.code_hash, i.code_size, i.code, i.language, i.text_feedback
           FROM individuals i
           WHERE i.run_id = $1
           ORDER BY i.generation ASC, i.combined_score DESC"#,
    )
    .bind(run_id)
    .fetch_all(state.db.pool())
    .await
    .map_err(|e| {
        tracing::error!("failed to list individuals: {e}");
        StatusCode::INTERNAL_SERVER_ERROR
    })?;

    let individuals: Vec<serde_json::Value> = rows
        .into_iter()
        .map(|r| {
            json!({
                "id": r.individual_id,
                "parent_id": r.parent_id,
                "code": r.code,
                "language": r.language,
                "generation": r.generation,
                "timestamp": r.timestamp,
                "agent_name": r.mutation_type,
                "combined_score": r.combined_score,
                "fitness_score": r.fitness_score,
                "metrics": r.metrics,
                "text_feedback": r.text_feedback,
                "metadata": {
                    "patch_name": r.mutation_type,
                    "patch_type": r.mutation_type,
                    "api_cost": r.api_cost,
                    "embed_cost": r.embed_cost,
                    "novelty_cost": r.novelty_cost,
                },
                "correct": r.correct,
                "is_pareto": r.is_pareto,
                "code_hash": r.code_hash,
                "code_size": r.code_size,
            })
        })
        .collect();

    Ok(Json(json!({"individuals": individuals})))
}

// --- Generations ---

async fn list_generations(
    State(state): State<Arc<AppState>>,
    Path(run_id): Path<uuid::Uuid>,
) -> Result<Json<serde_json::Value>, StatusCode> {
    let rows = sqlx::query_as::<_, GenerationRow>(
        r#"SELECT run_id, generation, timestamp, num_individuals,
                  best_score, avg_score, pareto_size, total_cost, metadata
           FROM generations
           WHERE run_id = $1
           ORDER BY generation ASC"#,
    )
    .bind(run_id)
    .fetch_all(state.db.pool())
    .await
    .map_err(|e| {
        tracing::error!("failed to list generations: {e}");
        StatusCode::INTERNAL_SERVER_ERROR
    })?;

    let generations: Vec<serde_json::Value> = rows
        .into_iter()
        .map(|r| {
            json!({
                "generation": r.generation,
                "timestamp": r.timestamp,
                "num_individuals": r.num_individuals,
                "best_score": r.best_score,
                "avg_score": r.avg_score,
                "pareto_size": r.pareto_size,
                "total_cost": r.total_cost,
                "metadata": r.metadata,
            })
        })
        .collect();

    Ok(Json(json!({"generations": generations})))
}

async fn get_generation(
    State(state): State<Arc<AppState>>,
    Path((run_id, generation)): Path<(uuid::Uuid, i32)>,
) -> Result<Json<serde_json::Value>, StatusCode> {
    let row = sqlx::query_as::<_, GenerationRow>(
        r#"SELECT run_id, generation, timestamp, num_individuals,
                  best_score, avg_score, pareto_size, total_cost, metadata
           FROM generations
           WHERE run_id = $1 AND generation = $2"#,
    )
    .bind(run_id)
    .bind(generation)
    .fetch_optional(state.db.pool())
    .await
    .map_err(|e| {
        tracing::error!("failed to get generation: {e}");
        StatusCode::INTERNAL_SERVER_ERROR
    })?
    .ok_or(StatusCode::NOT_FOUND)?;

    Ok(Json(json!({
        "generation": row.generation,
        "timestamp": row.timestamp,
        "num_individuals": row.num_individuals,
        "best_score": row.best_score,
        "avg_score": row.avg_score,
        "pareto_size": row.pareto_size,
        "total_cost": row.total_cost,
        "metadata": row.metadata,
    })))
}

// --- Lineage ---

async fn get_lineage(
    State(state): State<Arc<AppState>>,
    Path(run_id): Path<uuid::Uuid>,
) -> Result<Json<serde_json::Value>, StatusCode> {
    let rows = sqlx::query_as::<_, LineageRow>(
        r#"SELECT id, run_id, child_id, parent_id, generation,
                  mutation_type, timestamp, fitness_delta, edit_summary
           FROM code_lineages
           WHERE run_id = $1
           ORDER BY generation ASC"#,
    )
    .bind(run_id)
    .fetch_all(state.db.pool())
    .await
    .map_err(|e| {
        tracing::error!("failed to get lineage: {e}");
        StatusCode::INTERNAL_SERVER_ERROR
    })?;

    let edges: Vec<serde_json::Value> = rows
        .into_iter()
        .map(|r| {
            json!({
                "id": r.id,
                "child_id": r.child_id,
                "parent_id": r.parent_id,
                "generation": r.generation,
                "mutation_type": r.mutation_type,
                "fitness_delta": r.fitness_delta,
                "edit_summary": r.edit_summary,
            })
        })
        .collect();

    Ok(Json(json!({"edges": edges})))
}

// --- Row types ---

#[derive(sqlx::FromRow)]
struct EvolutionRunRow {
    run_id: uuid::Uuid,
    start_time: chrono::DateTime<chrono::Utc>,
    end_time: Option<chrono::DateTime<chrono::Utc>>,
    task_name: String,
    status: String,
    total_generations: i32,
    population_size: i32,
    config: serde_json::Value,
}

#[derive(sqlx::FromRow)]
struct IndividualApiRow {
    #[allow(dead_code)]
    run_id: uuid::Uuid,
    individual_id: uuid::Uuid,
    generation: i32,
    timestamp: chrono::DateTime<chrono::Utc>,
    parent_id: Option<uuid::Uuid>,
    mutation_type: String,
    fitness_score: f64,
    combined_score: f64,
    metrics: serde_json::Value,
    is_pareto: bool,
    correct: bool,
    api_cost: f64,
    embed_cost: f64,
    novelty_cost: f64,
    code_hash: String,
    code_size: i32,
    code: String,
    language: String,
    text_feedback: String,
}

#[derive(sqlx::FromRow)]
struct GenerationRow {
    #[allow(dead_code)]
    run_id: uuid::Uuid,
    generation: i32,
    timestamp: chrono::DateTime<chrono::Utc>,
    num_individuals: i32,
    best_score: f64,
    avg_score: f64,
    pareto_size: i32,
    total_cost: f64,
    metadata: serde_json::Value,
}

#[derive(sqlx::FromRow)]
struct LineageRow {
    id: uuid::Uuid,
    #[allow(dead_code)]
    run_id: uuid::Uuid,
    child_id: uuid::Uuid,
    parent_id: Option<uuid::Uuid>,
    generation: i32,
    mutation_type: String,
    #[allow(dead_code)]
    timestamp: chrono::DateTime<chrono::Utc>,
    fitness_delta: f64,
    edit_summary: String,
}
