//! Knuth-Morris-Pratt (KMP) string search.
//!
//! Finds all start indices where a pattern occurs in a text. Precomputes a
//! failure table (length of the longest proper prefix of the pattern that
//! is also a suffix) so the text pointer never moves backwards.
//!
//! Indices are character positions (not byte offsets), so the algorithm is
//! correct for any Unicode input.
//!
//! Time complexity:  O(n + m) where n = text length, m = pattern length
//! Space complexity: O(m) for the failure table

/// Return the KMP failure table for `pattern`.
///
/// `failure[i]` is the length of the longest proper prefix of
/// `pattern[..=i]` that is also a suffix of it.
fn build_failure_table(pattern: &[char]) -> Vec<usize> {
    let mut failure = vec![0usize; pattern.len()];
    let mut prefix_length = 0;

    for i in 1..pattern.len() {
        while prefix_length > 0 && pattern[i] != pattern[prefix_length] {
            prefix_length = failure[prefix_length - 1];
        }
        if pattern[i] == pattern[prefix_length] {
            prefix_length += 1;
        }
        failure[i] = prefix_length;
    }

    failure
}

/// Return all character start indices where `pattern` occurs in `text`.
///
/// An empty pattern matches nowhere by convention here.
fn kmp_search(text: &str, pattern: &str) -> Vec<usize> {
    let pattern: Vec<char> = pattern.chars().collect();
    if pattern.is_empty() {
        return Vec::new();
    }

    let failure = build_failure_table(&pattern);
    let mut matches = Vec::new();
    let mut matched = 0; // number of pattern characters currently matched

    for (i, ch) in text.chars().enumerate() {
        while matched > 0 && ch != pattern[matched] {
            matched = failure[matched - 1];
        }
        if ch == pattern[matched] {
            matched += 1;
        }
        if matched == pattern.len() {
            matches.push(i + 1 - pattern.len());
            matched = failure[matched - 1];
        }
    }

    matches
}

fn main() {
    assert!(kmp_search("ababcababcabc", "abc") == vec![2, 7, 10]);
    assert!(kmp_search("aaaaa", "aa") == vec![0, 1, 2, 3]); // overlapping matches
    assert!(kmp_search("hello", "world").is_empty());
    assert!(kmp_search("abc", "").is_empty());
    assert!(kmp_search("abc", "abcd").is_empty());
    assert!(kmp_search("abcabcabc", "abcabc") == vec![0, 3]);
    println!("kmp-string-search: all tests passed");
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn finds_all_matches() {
        assert_eq!(kmp_search("ababcababcabc", "abc"), vec![2, 7, 10]);
        assert_eq!(kmp_search("aaaaa", "aa"), vec![0, 1, 2, 3]);
        assert_eq!(kmp_search("abcabcabc", "abcabc"), vec![0, 3]);
    }

    #[test]
    fn edge_cases() {
        assert!(kmp_search("hello", "world").is_empty());
        assert!(kmp_search("abc", "").is_empty());
        assert!(kmp_search("abc", "abcd").is_empty());
    }

    #[test]
    fn failure_table() {
        let pattern: Vec<char> = "abacaba".chars().collect();
        assert_eq!(build_failure_table(&pattern), vec![0, 0, 1, 0, 1, 2, 3]);
    }
}
