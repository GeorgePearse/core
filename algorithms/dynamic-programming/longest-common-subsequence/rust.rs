//! Longest Common Subsequence (LCS).
//!
//! Computes the longest subsequence (in-order, not necessarily contiguous)
//! common to two strings, returning the subsequence itself by backtracking
//! through the DP table.
//!
//! Time complexity:  O(m * n)
//! Space complexity: O(m * n)

/// Return the longest common subsequence of `first` and `second`.
///
/// `dp[i][j]` holds the LCS length of the first `i` chars of `first`
/// and the first `j` chars of `second`.
fn longest_common_subsequence(first: &str, second: &str) -> String {
    let a: Vec<char> = first.chars().collect();
    let b: Vec<char> = second.chars().collect();
    let (m, n) = (a.len(), b.len());

    let mut dp = vec![vec![0usize; n + 1]; m + 1];
    for i in 1..=m {
        for j in 1..=n {
            dp[i][j] = if a[i - 1] == b[j - 1] {
                dp[i - 1][j - 1] + 1
            } else {
                dp[i - 1][j].max(dp[i][j - 1])
            };
        }
    }

    // Backtrack from dp[m][n] to reconstruct the subsequence.
    let mut result: Vec<char> = Vec::with_capacity(dp[m][n]);
    let (mut i, mut j) = (m, n);
    while i > 0 && j > 0 {
        if a[i - 1] == b[j - 1] {
            result.push(a[i - 1]);
            i -= 1;
            j -= 1;
        } else if dp[i - 1][j] >= dp[i][j - 1] {
            i -= 1;
        } else {
            j -= 1;
        }
    }

    result.into_iter().rev().collect()
}

fn main() {
    assert!(longest_common_subsequence("ABCBDAB", "BDCABA") == "BCBA");
    assert!(longest_common_subsequence("AGGTAB", "GXTXAYB") == "GTAB");
    assert!(longest_common_subsequence("", "ABC").is_empty());
    assert!(longest_common_subsequence("ABC", "ABC") == "ABC");
    assert!(longest_common_subsequence("ABC", "XYZ").is_empty());
    println!("longest-common-subsequence: all tests passed");
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn known_subsequences() {
        assert_eq!(longest_common_subsequence("ABCBDAB", "BDCABA"), "BCBA");
        assert_eq!(longest_common_subsequence("AGGTAB", "GXTXAYB"), "GTAB");
    }

    #[test]
    fn edge_cases() {
        assert_eq!(longest_common_subsequence("", "ABC"), "");
        assert_eq!(longest_common_subsequence("ABC", "ABC"), "ABC");
        assert_eq!(longest_common_subsequence("ABC", "XYZ"), "");
    }
}
