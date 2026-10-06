use genesis_rust_backend::core::alma_memory::AlmaMemorySystem;
use genesis_rust_backend::core::gepa_optimizer::GepaStyleOptimizer;

#[test]
fn alma_builds_context() {
    let mut alma = AlmaMemorySystem::new(true, 16, 3, 0.01);
    alma.observe_outcome(
        2,
        0.3,
        0.6,
        true,
        "diff",
        "vectorize-loop",
        "vectorized inner loop",
        "edits=3",
        "speed improved",
        "",
    );

    let ctx = alma
        .build_prompt_context(3, "fn vectorize_loop() {}", "need speed")
        .expect("context");
    assert!(ctx.contains("ALMA Long-Term Memory"));
}

#[test]
fn gepa_returns_candidate_and_fewshot() {
    let mut gepa = GepaStyleOptimizer::new(true, 2, 16, 0.0, 1.1, None);
    let ctx = gepa.build_prompt_context();
    assert!(ctx.candidate_id.is_some());

    gepa.observe_result(
        2,
        0.3,
        0.8,
        "diff",
        "good-change",
        "helped",
        "edits=2",
        ctx.candidate_id,
        true,
    );

    let ctx2 = gepa.build_prompt_context();
    assert!(ctx2
        .fewshot_examples
        .unwrap_or_default()
        .contains("Successful Trace"));
}
