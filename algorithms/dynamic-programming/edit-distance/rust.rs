//! Edit distance (Levenshtein distance).
//!
//! Computes the minimum number of single-character insertions, deletions,
//! and substitutions (all unit cost) needed to transform one string into
//! another, using the classic bottom-up DP table.
//!
//! Time complexity:  O(m * n)
//! Space complexity: O(m * n)

/// Return the Levenshtein distance between `source` and `target`.
///
/// `dp[i][j]` holds the edit distance between the first `i` chars of
/// `source` and the first `j` chars of `target`.
fn edit_distance(source: &str, target: &str) -> usize {
    let a: Vec<char> = source.chars().collect();
    let b: Vec<char> = target.chars().collect();
    let (m, n) = (a.len(), b.len());

    let mut dp = vec![vec![0usize; n + 1]; m + 1];

    // Transforming a prefix into the empty string takes i deletions,
    // and the empty string into a prefix takes j insertions.
    for i in 0..=m {
        dp[i][0] = i;
    }
    for j in 0..=n {
        dp[0][j] = j;
    }

    for i in 1..=m {
        for j in 1..=n {
            dp[i][j] = if a[i - 1] == b[j - 1] {
                dp[i - 1][j - 1]
            } else {
                1 + dp[i - 1][j] // delete source[i - 1]
                    .min(dp[i][j - 1]) // insert target[j - 1]
                    .min(dp[i - 1][j - 1]) // substitute
            };
        }
    }

    dp[m][n]
}

fn main() {
    assert!(edit_distance("kitten", "sitting") == 3);
    assert!(edit_distance("flaw", "lawn") == 2);
    assert!(edit_distance("", "abc") == 3);
    assert!(edit_distance("abc", "") == 3);
    assert!(edit_distance("same", "same") == 0);
    assert!(edit_distance("intention", "execution") == 5);
    println!("edit-distance: all tests passed");
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn known_distances() {
        assert_eq!(edit_distance("kitten", "sitting"), 3);
        assert_eq!(edit_distance("flaw", "lawn"), 2);
        assert_eq!(edit_distance("intention", "execution"), 5);
    }

    #[test]
    fn edge_cases() {
        assert_eq!(edit_distance("", "abc"), 3);
        assert_eq!(edit_distance("abc", ""), 3);
        assert_eq!(edit_distance("same", "same"), 0);
    }
}
