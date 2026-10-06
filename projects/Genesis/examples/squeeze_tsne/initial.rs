// Standalone t-SNE gradient implementation for Genesis optimization
// This file can be compiled with: rustc -O initial.rs -o tsne
//
// The gradient computation is O(n^2) and called 1000+ times per embedding.
// Optimizing this is critical for t-SNE performance.

use std::fs::File;
use std::io::{BufRead, BufReader, Write};

// Simple 2D array using flat Vec
struct Array2 {
    data: Vec<f64>,
    rows: usize,
    cols: usize,
}

impl Array2 {
    fn zeros(rows: usize, cols: usize) -> Self {
        Self {
            data: vec![0.0; rows * cols],
            rows,
            cols,
        }
    }

    fn get(&self, i: usize, j: usize) -> f64 {
        self.data[i * self.cols + j]
    }

    fn set(&mut self, i: usize, j: usize, val: f64) {
        self.data[i * self.cols + j] = val;
    }
}

// EVOLVE-BLOCK-START
/// Compute t-SNE gradient for a single point
///
/// This is the hottest code path - called n times per iteration, 1000+ iterations.
/// The gradient formula is: grad_i = 4 * sum_j[(p_ij - q_ij) * (1 + ||y_i - y_j||^2)^-1 * (y_i - y_j)]
///
/// Optimization opportunities:
/// 1. Loop unrolling for n_components (typically 2)
/// 2. SIMD for distance computation
/// 3. Early termination when contribution is negligible
/// 4. Cache-friendly memory access patterns
/// 5. Pre-compute repeated values
fn compute_gradient_for_point(
    point_idx: usize,
    n_points: usize,
    n_components: usize,
    pq: &Array2,        // P - Q matrix (n x n)
    y: &Array2,         // Current embedding (n x n_components)
) -> Vec<f64> {
    let mut grad = vec![0.0; n_components];

    for j in 0..n_points {
        if point_idx == j {
            continue;
        }

        // Compute squared distance in embedding space
        let mut dist_sq = 0.0;
        for k in 0..n_components {
            let diff = y.get(point_idx, k) - y.get(j, k);
            dist_sq += diff * diff;
        }

        // Student t-distribution kernel: (1 + d^2)^-1
        let kernel = 1.0 / (1.0 + dist_sq);

        // Gradient contribution from this pair
        let mult = 4.0 * pq.get(point_idx, j) * kernel;

        for k in 0..n_components {
            grad[k] += mult * (y.get(point_idx, k) - y.get(j, k));
        }
    }

    grad
}

/// Compute full gradient matrix
/// Returns gradient for all points (n x n_components)
fn compute_gradient(
    n_points: usize,
    n_components: usize,
    p: &Array2,    // Joint probabilities in high-d (n x n)
    q: &Array2,    // Joint probabilities in low-d (n x n)
    y: &Array2,    // Current embedding (n x n_components)
) -> Array2 {
    // Pre-compute P - Q
    let mut pq = Array2::zeros(n_points, n_points);
    for i in 0..n_points {
        for j in 0..n_points {
            pq.set(i, j, p.get(i, j) - q.get(i, j));
        }
    }

    // Compute gradient for each point
    let mut grad = Array2::zeros(n_points, n_components);
    for i in 0..n_points {
        let point_grad = compute_gradient_for_point(i, n_points, n_components, &pq, y);
        for k in 0..n_components {
            grad.set(i, k, point_grad[k]);
        }
    }

    grad
}
// EVOLVE-BLOCK-END

/// Compute Q distribution (Student t-distribution in low-d space)
fn compute_q(y: &Array2, n_points: usize, n_components: usize) -> Array2 {
    let mut q = Array2::zeros(n_points, n_points);
    let mut sum_q = 0.0;

    // Compute unnormalized Q
    for i in 0..n_points {
        for j in (i + 1)..n_points {
            let mut dist_sq = 0.0;
            for k in 0..n_components {
                let diff = y.get(i, k) - y.get(j, k);
                dist_sq += diff * diff;
            }
            let qij = 1.0 / (1.0 + dist_sq);
            q.set(i, j, qij);
            q.set(j, i, qij);
            sum_q += 2.0 * qij;
        }
    }

    // Normalize
    if sum_q > 0.0 {
        for i in 0..n_points {
            for j in 0..n_points {
                let val = q.get(i, j) / sum_q;
                q.set(i, j, val.max(1e-12));
            }
        }
    }

    q
}

/// Compute pairwise Euclidean distances (squared)
fn compute_pairwise_distances(data: &[Vec<f64>]) -> Array2 {
    let n = data.len();
    let mut distances = Array2::zeros(n, n);

    for i in 0..n {
        for j in (i + 1)..n {
            let mut dist_sq = 0.0;
            for k in 0..data[i].len() {
                let diff = data[i][k] - data[j][k];
                dist_sq += diff * diff;
            }
            distances.set(i, j, dist_sq);
            distances.set(j, i, dist_sq);
        }
    }

    distances
}

/// Compute joint probabilities P using perplexity-based binary search
fn compute_joint_probabilities(distances: &Array2, n_points: usize, perplexity: f64) -> Array2 {
    let target_entropy = perplexity.ln();
    let mut p = Array2::zeros(n_points, n_points);

    // Compute P(j|i) for each i
    for i in 0..n_points {
        let mut beta = 1.0;
        let mut beta_min = f64::NEG_INFINITY;
        let mut beta_max = f64::INFINITY;

        let mut p_row = vec![0.0; n_points];

        // Binary search for sigma
        for _ in 0..50 {
            let mut sum_p = 0.0;
            for j in 0..n_points {
                if i != j {
                    let pij = (-beta * distances.get(i, j)).exp();
                    p_row[j] = pij;
                    sum_p += pij;
                }
            }

            // Normalize
            if sum_p > 1e-10 {
                for j in 0..n_points {
                    p_row[j] /= sum_p;
                }
            }

            // Compute entropy
            let mut entropy = 0.0;
            for j in 0..n_points {
                if p_row[j] > 1e-10 {
                    entropy -= p_row[j] * p_row[j].ln();
                }
            }

            let entropy_diff = entropy - target_entropy;
            if entropy_diff.abs() < 1e-5 {
                break;
            }

            if entropy_diff > 0.0 {
                beta_min = beta;
                beta = if beta_max.is_infinite() { beta * 2.0 } else { (beta + beta_max) / 2.0 };
            } else {
                beta_max = beta;
                beta = if beta_min.is_infinite() { beta / 2.0 } else { (beta + beta_min) / 2.0 };
            }
        }

        for j in 0..n_points {
            p.set(i, j, p_row[j]);
        }
    }

    // Symmetrize: P = (P + P^T) / (2n)
    let mut p_sym = Array2::zeros(n_points, n_points);
    for i in 0..n_points {
        for j in 0..n_points {
            let val = (p.get(i, j) + p.get(j, i)) / (2.0 * n_points as f64);
            p_sym.set(i, j, val.max(1e-12));
        }
    }

    p_sym
}

/// Simple LCG random number generator (seeded for reproducibility)
struct Rng {
    state: u64,
}

impl Rng {
    fn new(seed: u64) -> Self {
        Self { state: seed }
    }

    fn next_f64(&mut self) -> f64 {
        // LCG parameters (same as glibc)
        self.state = self.state.wrapping_mul(1103515245).wrapping_add(12345);
        (self.state as f64) / (u64::MAX as f64)
    }

    fn normal(&mut self) -> f64 {
        // Box-Muller transform
        let u1 = self.next_f64().max(1e-10);
        let u2 = self.next_f64();
        (-2.0 * u1.ln()).sqrt() * (2.0 * std::f64::consts::PI * u2).cos()
    }
}

/// Run t-SNE embedding
fn run_tsne(
    data: &[Vec<f64>],
    n_components: usize,
    perplexity: f64,
    n_iter: usize,
    learning_rate: f64,
    seed: u64,
) -> Array2 {
    let n_points = data.len();

    // Compute pairwise distances
    let distances = compute_pairwise_distances(data);

    // Compute joint probabilities P
    let p = compute_joint_probabilities(&distances, n_points, perplexity);

    // Initialize embedding randomly
    let mut rng = Rng::new(seed);
    let mut y = Array2::zeros(n_points, n_components);
    for i in 0..n_points {
        for k in 0..n_components {
            y.set(i, k, rng.normal() * 1e-4);
        }
    }

    // Gradient descent parameters
    let early_exaggeration = 12.0;
    let momentum = 0.5;
    let final_momentum = 0.8;
    let momentum_switch_iter = 250;

    let mut gains = vec![vec![1.0; n_components]; n_points];
    let mut y_incs = Array2::zeros(n_points, n_components);

    for iter in 0..n_iter {
        // Scale P during early exaggeration
        let p_scaled = if iter < 250 {
            let mut ps = Array2::zeros(n_points, n_points);
            for i in 0..n_points {
                for j in 0..n_points {
                    ps.set(i, j, p.get(i, j) * early_exaggeration);
                }
            }
            ps
        } else {
            let mut ps = Array2::zeros(n_points, n_points);
            for i in 0..n_points {
                for j in 0..n_points {
                    ps.set(i, j, p.get(i, j));
                }
            }
            ps
        };

        // Compute Q distribution
        let q = compute_q(&y, n_points, n_components);

        // Compute gradient (this is the hot path we're optimizing!)
        let grad = compute_gradient(n_points, n_components, &p_scaled, &q, &y);

        // Update gains
        for i in 0..n_points {
            for k in 0..n_components {
                let sign_match = (grad.get(i, k) > 0.0) == (y_incs.get(i, k) > 0.0);
                gains[i][k] = if sign_match {
                    f64::max(gains[i][k] * 0.8, 0.01)
                } else {
                    gains[i][k] + 0.2
                };
            }
        }

        // Update momentum
        let current_momentum = if iter < momentum_switch_iter {
            momentum
        } else {
            final_momentum
        };

        // Update positions
        for i in 0..n_points {
            for k in 0..n_components {
                let inc = current_momentum * y_incs.get(i, k) - learning_rate * gains[i][k] * grad.get(i, k);
                y_incs.set(i, k, inc);
                y.set(i, k, y.get(i, k) + inc);
            }
        }

        // Center embedding
        let mut mean = vec![0.0; n_components];
        for i in 0..n_points {
            for k in 0..n_components {
                mean[k] += y.get(i, k);
            }
        }
        for k in 0..n_components {
            mean[k] /= n_points as f64;
        }
        for i in 0..n_points {
            for k in 0..n_components {
                y.set(i, k, y.get(i, k) - mean[k]);
            }
        }
    }

    y
}

/// Compute trustworthiness metric (measures how well local structure is preserved)
fn compute_trustworthiness(
    high_d_data: &[Vec<f64>],
    embedding: &Array2,
    k: usize,
) -> f64 {
    let n = high_d_data.len();
    let n_components = embedding.cols;

    // Get k-nearest neighbors in original space
    let mut high_d_neighbors: Vec<Vec<usize>> = Vec::new();
    for i in 0..n {
        let mut dists: Vec<(usize, f64)> = (0..n)
            .filter(|&j| j != i)
            .map(|j| {
                let mut d = 0.0;
                for dim in 0..high_d_data[i].len() {
                    let diff = high_d_data[i][dim] - high_d_data[j][dim];
                    d += diff * diff;
                }
                (j, d)
            })
            .collect();
        dists.sort_by(|a, b| a.1.partial_cmp(&b.1).unwrap());
        high_d_neighbors.push(dists.iter().take(k).map(|(idx, _)| *idx).collect());
    }

    // Get k-nearest neighbors in embedding space
    let mut low_d_neighbors: Vec<Vec<usize>> = Vec::new();
    for i in 0..n {
        let mut dists: Vec<(usize, f64)> = (0..n)
            .filter(|&j| j != i)
            .map(|j| {
                let mut d = 0.0;
                for dim in 0..n_components {
                    let diff = embedding.get(i, dim) - embedding.get(j, dim);
                    d += diff * diff;
                }
                (j, d)
            })
            .collect();
        dists.sort_by(|a, b| a.1.partial_cmp(&b.1).unwrap());
        low_d_neighbors.push(dists.iter().take(k).map(|(idx, _)| *idx).collect());
    }

    // Compute trustworthiness
    let mut error = 0.0;
    for i in 0..n {
        let high_d_set: std::collections::HashSet<_> = high_d_neighbors[i].iter().collect();
        for (rank, &j) in low_d_neighbors[i].iter().enumerate() {
            if !high_d_set.contains(&j) {
                // Find rank in original space
                let orig_rank = (0..n)
                    .filter(|&m| m != i)
                    .position(|m| {
                        let mut d = 0.0;
                        for dim in 0..high_d_data[i].len() {
                            let diff = high_d_data[i][dim] - high_d_data[m][dim];
                            d += diff * diff;
                        }
                        // Check if this is the j-th point
                        m == j
                    })
                    .unwrap_or(n - 1);
                error += (orig_rank.saturating_sub(k)) as f64;
            }
        }
    }

    let norm = (2.0 / (n as f64 * k as f64 * (2.0 * n as f64 - 3.0 * k as f64 - 1.0))).max(1e-10);
    1.0 - norm * error
}

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
        if line.trim().is_empty() {
            continue;
        }
        let values: Vec<f64> = line
            .split_whitespace()
            .filter_map(|s| s.parse().ok())
            .collect();
        if !values.is_empty() {
            data.push(values);
        }
    }

    let n_points = data.len();
    let n_dims = if data.is_empty() { 0 } else { data[0].len() };

    eprintln!("Loaded {} points with {} dimensions", n_points, n_dims);

    // Run t-SNE
    let start = std::time::Instant::now();
    let embedding = run_tsne(
        &data,
        2,          // n_components
        30.0,       // perplexity
        500,        // n_iter (reduced for testing)
        200.0,      // learning_rate
        42,         // seed
    );
    let elapsed = start.elapsed();

    eprintln!("t-SNE completed in {:.3}s", elapsed.as_secs_f64());

    // Compute trustworthiness
    let trust = compute_trustworthiness(&data, &embedding, 10);
    eprintln!("Trustworthiness (k=10): {:.4}", trust);

    // Write output as JSON
    let mut output = File::create(output_file).expect("Failed to create output file");
    writeln!(output, "{{").unwrap();
    writeln!(output, "  \"embedding\": [").unwrap();
    for i in 0..n_points {
        let mut row = Vec::new();
        for k in 0..2 {
            row.push(format!("{:.6}", embedding.get(i, k)));
        }
        let comma = if i < n_points - 1 { "," } else { "" };
        writeln!(output, "    [{}]{}", row.join(", "), comma).unwrap();
    }
    writeln!(output, "  ],").unwrap();
    writeln!(output, "  \"trustworthiness\": {:.6},", trust).unwrap();
    writeln!(output, "  \"time_seconds\": {:.6}", elapsed.as_secs_f64()).unwrap();
    writeln!(output, "}}").unwrap();
}
