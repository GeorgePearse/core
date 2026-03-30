mod common;

use genesis_rust_backend::database::PgProgramDatabase;
use serde_json::json;
use uuid::Uuid;

async fn db_from_test() -> PgProgramDatabase {
    let test_db = common::TestDb::new().await;
    // Leak the container handle so it stays alive for the test duration.
    // Each test gets its own container so there is no cross-contamination.
    let pool = test_db.pool.clone();
    std::mem::forget(test_db);
    PgProgramDatabase::from_pool(pool)
}

#[tokio::test]
async fn create_and_list_evolution_run() {
    let db = db_from_test().await;

    let run_id = db
        .create_evolution_run(
            "circle_packing",
            &json!({"lr": 0.01}),
            20,
            Some("local"),
            None,
        )
        .await
        .expect("create_evolution_run failed");

    let row =
        sqlx::query_scalar::<_, String>("SELECT task_name FROM evolution_runs WHERE run_id = $1")
            .bind(run_id)
            .fetch_one(db.pool())
            .await
            .expect("fetch failed");

    assert_eq!(row, "circle_packing");
}

#[tokio::test]
async fn update_evolution_run_status() {
    let db = db_from_test().await;

    let run_id = db
        .create_evolution_run("test_task", &json!({}), 10, None, None)
        .await
        .unwrap();

    db.update_evolution_run_status(run_id, "completed", 5)
        .await
        .unwrap();

    let (status, gens) = sqlx::query_as::<_, (String, i32)>(
        "SELECT status, total_generations FROM evolution_runs WHERE run_id = $1",
    )
    .bind(run_id)
    .fetch_one(db.pool())
    .await
    .unwrap();

    assert_eq!(status, "completed");
    assert_eq!(gens, 5);
}

#[tokio::test]
async fn add_and_get_best_individual() {
    let db = db_from_test().await;

    let run_id = db
        .create_evolution_run("test_task", &json!({}), 10, None, None)
        .await
        .unwrap();

    let id_a = Uuid::new_v4();
    let id_b = Uuid::new_v4();

    db.add_individual(
        run_id,
        id_a,
        0,
        None,
        "diff",
        0.5,
        0.5,
        &json!({"acc": 0.5}),
        false,
        true,
        0.01,
        0.0,
        0.0,
        "aaa",
        100,
        "print('hello')",
        "python",
        "",
    )
    .await
    .unwrap();

    db.add_individual(
        run_id,
        id_b,
        1,
        Some(id_a),
        "full",
        0.9,
        0.9,
        &json!({"acc": 0.9}),
        true,
        true,
        0.02,
        0.0,
        0.0,
        "bbb",
        120,
        "print('world')",
        "python",
        "looks good",
    )
    .await
    .unwrap();

    let best = db.get_best_individual(run_id).await.unwrap().unwrap();
    assert_eq!(best.individual_id, id_b);
    assert!((best.combined_score - 0.9).abs() < 1e-9);
}

#[tokio::test]
async fn get_top_individuals_ordering() {
    let db = db_from_test().await;

    let run_id = db
        .create_evolution_run("test_task", &json!({}), 10, None, None)
        .await
        .unwrap();

    for i in 0..5 {
        db.add_individual(
            run_id,
            Uuid::new_v4(),
            i,
            None,
            "diff",
            i as f64 * 0.1,
            i as f64 * 0.1,
            &json!({}),
            false,
            false,
            0.0,
            0.0,
            0.0,
            &format!("hash_{i}"),
            100,
            &format!("code_{i}"),
            "python",
            "",
        )
        .await
        .unwrap();
    }

    let top = db.get_top_individuals(run_id, 3).await.unwrap();
    assert_eq!(top.len(), 3);
    assert!(top[0].combined_score >= top[1].combined_score);
    assert!(top[1].combined_score >= top[2].combined_score);
}

#[tokio::test]
async fn log_generation() {
    let db = db_from_test().await;

    let run_id = db
        .create_evolution_run("test_task", &json!({}), 10, None, None)
        .await
        .unwrap();

    db.log_generation(run_id, 0, 10, 0.8, 0.5, 3, 0.1, &json!({"note": "gen0"}))
        .await
        .unwrap();

    let count = sqlx::query_scalar::<_, i64>("SELECT COUNT(*) FROM generations WHERE run_id = $1")
        .bind(run_id)
        .fetch_one(db.pool())
        .await
        .unwrap();

    assert_eq!(count, 1);
}

#[tokio::test]
async fn log_pareto_front() {
    let db = db_from_test().await;

    let run_id = db
        .create_evolution_run("test_task", &json!({}), 10, None, None)
        .await
        .unwrap();

    let ind_id = Uuid::new_v4();
    db.log_pareto_front(run_id, 0, ind_id, 0.8, 0.75, &json!({}))
        .await
        .unwrap();

    let count =
        sqlx::query_scalar::<_, i64>("SELECT COUNT(*) FROM pareto_fronts WHERE run_id = $1")
            .bind(run_id)
            .fetch_one(db.pool())
            .await
            .unwrap();

    assert_eq!(count, 1);
}

#[tokio::test]
async fn log_lineage() {
    let db = db_from_test().await;

    let run_id = db
        .create_evolution_run("test_task", &json!({}), 10, None, None)
        .await
        .unwrap();

    let child = Uuid::new_v4();
    let parent = Uuid::new_v4();
    db.log_lineage(run_id, child, Some(parent), 1, "diff", 0.1, "improved loop")
        .await
        .unwrap();

    let count =
        sqlx::query_scalar::<_, i64>("SELECT COUNT(*) FROM code_lineages WHERE run_id = $1")
            .bind(run_id)
            .fetch_one(db.pool())
            .await
            .unwrap();

    assert_eq!(count, 1);
}

#[tokio::test]
async fn log_llm_interaction() {
    let db = db_from_test().await;

    db.log_llm_interaction(
        "gpt-4",
        &json!([{"role": "user", "content": "hello"}]),
        "response text",
        "thought text",
        0.005,
        1.2,
        &json!({}),
    )
    .await
    .unwrap();

    let count = sqlx::query_scalar::<_, i64>("SELECT COUNT(*) FROM llm_logs")
        .fetch_one(db.pool())
        .await
        .unwrap();

    assert_eq!(count, 1);
}

#[tokio::test]
async fn log_agent_action() {
    let db = db_from_test().await;

    db.log_agent_action("mutate", &json!({"gen": 3}), &json!({}))
        .await
        .unwrap();

    let count = sqlx::query_scalar::<_, i64>("SELECT COUNT(*) FROM agent_actions")
        .fetch_one(db.pool())
        .await
        .unwrap();

    assert_eq!(count, 1);
}
