// Dimensionality Reduction Optimization Task
// Goal: Minimize stress/error while maximizing trustworthiness and spearman correlation, and minimizing time.
//
// This initial implementation uses a simple Force-Directed Layout (Spring Embedding).
// It converts high-dimensional distances to target springs and relaxes the system.

use std::fs::File;
use std::io::{BufRead, BufReader, Write};
use std::time::Instant;

// Simple random number generator
struct Rng {
    state: u64,
}

impl Rng {
    fn new(seed: u64) -> Self {
        Self { state: seed }
    }

    fn next_f64(&mut self) -> f64 {
        self.state = self.state.wrapping_mul(6364136223846793005).wrapping_add(1442695040888963407);
        (self.state as f64) / (u64::MAX as f64)
    }
}

// EVOLVE-BLOCK-START
fn run_dimensionality_reduction(
    data: &[Vec<f64>],
    n_components: usize,
    seed: u64,
) -> Vec<Vec<f64>> {
    let n = data.len();
    let mut rng = Rng::new(seed);

    // Initialize random embedding
    let mut embedding = vec![vec![0.0; n_components]; n];
    for i in 0..n {
        for j in 0..n_components {
            embedding[i][j] = rng.next_f64();
        }
    }

    // Simple Force-Directed Graph Layout / MDS-like optimization
    // Minimize (dist_high - dist_low)^2
    let learning_rate = 0.1;
    let n_iter = 100;

    // Pre-compute high-D distances (brute force O(N^2))
    // Note: For large N, this is slow.
    let mut target_dists = vec![vec![0.0; n]; n];
    for i in 0..n {
        for j in (i + 1)..n {
            let d: f64 = data[i].iter().zip(&data[j]).map(|(a, b)| (a - b).powi(2)).sum();
            let d = d.sqrt();
            target_dists[i][j] = d;
            target_dists[j][i] = d;
        }
    }

    for _iter in 0..n_iter {
        let mut grads = vec![vec![0.0; n_components]; n];
        let mut total_error = 0.0;

        for i in 0..n {
            for j in 0..n {
                if i == j { continue; }

                let mut dist_sq = 0.0;
                for k in 0..n_components {
                    dist_sq += (embedding[i][k] - embedding[j][k]).powi(2);
                }
                let dist = dist_sq.sqrt().max(1e-6);
                let target = target_dists[i][j];

                // Stress = (dist - target)^2
                // dStress/dPos = 2 * (dist - target) * (pos_i - pos_j) / dist
                let diff = dist - target;
                total_error += diff * diff;

                let factor = 2.0 * diff / dist;
                for k in 0..n_components {
                    grads[i][k] += factor * (embedding[i][k] - embedding[j][k]);
                }
            }
        }

        // Update positions
        for i in 0..n {
            for k in 0..n_components {
                embedding[i][k] -= learning_rate * grads[i][k];
            }
        }
    }

    embedding
}
// EVOLVE-BLOCK-END

fn main() {
    let args: Vec<String> = std::env::args().collect();
    if args.len() < 3 {
        eprintln!("Usage: {} <data_file> <output_file>", args[0]);
        std::process::exit(1);
    }

    let data_file = &args[1];
    let output_file = &args[2];

    // Load data
    let file = File::open(data_file).expect("Failed to open data file");
    let reader = BufReader::new(file);
    let mut data: Vec<Vec<f64>> = Vec::new();

    for line in reader.lines() {
        let line = line.expect("Failed to read line");
        if line.trim().is_empty() { continue; }
        let values: Vec<f64> = line.split_whitespace()
            .filter_map(|s| s.parse().ok())
            .collect();
        if !values.is_empty() {
            data.push(values);
        }
    }

    let start = Instant::now();
    let embedding = run_dimensionality_reduction(&data, 2, 42);
    let duration = start.elapsed();

    eprintln!("Execution time: {:.3}s", duration.as_secs_f64());

    // Write output JSON
    let mut output = File::create(output_file).expect("Failed to create output file");
    writeln!(output, "{{").unwrap();
    writeln!(output, "  \"time_seconds\": {:.6},", duration.as_secs_f64()).unwrap();
    writeln!(output, "  \"embedding\": [").unwrap();
    for (i, point) in embedding.iter().enumerate() {
        let coords: Vec<String> = point.iter().map(|v| format!("{:.6}", v)).collect();
        let comma = if i < embedding.len() - 1 { "," } else { "" };
        writeln!(output, "    [{}]{}", coords.join(", "), comma).unwrap();
    }
    writeln!(output, "  ]").unwrap();
    writeln!(output, "}}").unwrap();
}
