//! 0/1 Knapsack.
//!
//! Given items with weights and values and a knapsack capacity, selects a
//! subset of items (each used at most once) that maximizes total value
//! without exceeding the capacity. Bottom-up DP table; returns the maximum
//! achievable value.
//!
//! Time complexity:  O(n * W) where n is the item count and W the capacity
//! Space complexity: O(n * W)

/// Return the maximum total value achievable within `capacity`.
///
/// `dp[i][w]` holds the best value using the first `i` items with
/// capacity `w`. Panics if `weights` and `values` differ in length.
fn knapsack_01(weights: &[usize], values: &[u64], capacity: usize) -> u64 {
    assert_eq!(
        weights.len(),
        values.len(),
        "weights and values must have the same length"
    );

    let item_count = weights.len();
    let mut dp = vec![vec![0u64; capacity + 1]; item_count + 1];

    for i in 1..=item_count {
        let (weight, value) = (weights[i - 1], values[i - 1]);
        for w in 0..=capacity {
            // Option 1: skip item i.
            dp[i][w] = dp[i - 1][w];
            // Option 2: take item i, if it fits.
            if weight <= w {
                dp[i][w] = dp[i][w].max(dp[i - 1][w - weight] + value);
            }
        }
    }

    dp[item_count][capacity]
}

fn main() {
    assert!(knapsack_01(&[1, 3, 4, 5], &[1, 4, 5, 7], 7) == 9);
    assert!(knapsack_01(&[10, 20, 30], &[60, 100, 120], 50) == 220);
    assert!(knapsack_01(&[], &[], 10) == 0);
    assert!(knapsack_01(&[5], &[100], 4) == 0);
    assert!(knapsack_01(&[2, 2, 2], &[10, 10, 10], 6) == 30);
    println!("knapsack-01: all tests passed");
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn known_instances() {
        assert_eq!(knapsack_01(&[1, 3, 4, 5], &[1, 4, 5, 7], 7), 9);
        assert_eq!(knapsack_01(&[10, 20, 30], &[60, 100, 120], 50), 220);
    }

    #[test]
    fn edge_cases() {
        assert_eq!(knapsack_01(&[], &[], 10), 0);
        assert_eq!(knapsack_01(&[5], &[100], 4), 0);
        assert_eq!(knapsack_01(&[2, 2, 2], &[10, 10, 10], 6), 30);
    }
}
