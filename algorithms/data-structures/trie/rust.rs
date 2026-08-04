//! Trie (prefix tree) over lowercase words.
//!
//! Supports insert, exact-word search, and prefix search (starts_with), each
//! in time proportional to the length of the word or prefix. Children are
//! stored in a fixed 26-slot array indexed by `letter - 'a'`.
//!
//! Complexity: O(m) per operation where m is the word length;
//! O(total characters stored) space.

const ALPHABET_SIZE: usize = 26;

#[derive(Default)]
struct TrieNode {
    children: [Option<Box<TrieNode>>; ALPHABET_SIZE],
    is_end_of_word: bool,
}

#[derive(Default)]
pub struct Trie {
    root: TrieNode,
}

/// Map a lowercase ASCII letter to its child-array index.
fn char_index(c: char) -> usize {
    debug_assert!(c.is_ascii_lowercase(), "trie only stores lowercase a-z");
    (c as u8 - b'a') as usize
}

impl Trie {
    pub fn new() -> Self {
        Trie::default()
    }

    /// Add `word` (lowercase a-z) to the trie.
    pub fn insert(&mut self, word: &str) {
        let mut node = &mut self.root;
        for c in word.chars() {
            node = node.children[char_index(c)].get_or_insert_with(Box::default);
        }
        node.is_end_of_word = true;
    }

    /// Return `true` if `word` was previously inserted as a complete word.
    pub fn search(&self, word: &str) -> bool {
        self.walk(word).is_some_and(|node| node.is_end_of_word)
    }

    /// Return `true` if any inserted word starts with `prefix`.
    pub fn starts_with(&self, prefix: &str) -> bool {
        self.walk(prefix).is_some()
    }

    /// Follow `key` character by character; return the final node if present.
    fn walk(&self, key: &str) -> Option<&TrieNode> {
        let mut node = &self.root;
        for c in key.chars() {
            node = node.children[char_index(c)].as_deref()?;
        }
        Some(node)
    }
}

fn main() {
    let mut trie = Trie::new();
    trie.insert("apple");
    assert!(trie.search("apple"));
    assert!(!trie.search("app")); // prefix only, not a full word
    assert!(trie.starts_with("app"));
    assert!(!trie.starts_with("banana"));

    trie.insert("app");
    assert!(trie.search("app"));

    trie.insert("application");
    assert!(trie.search("application"));
    assert!(trie.starts_with("appl"));
    assert!(!trie.search("appl"));
    assert!(trie.starts_with("")); // empty prefix matches everything

    println!("trie: all tests passed");
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn search_distinguishes_word_from_prefix() {
        let mut trie = Trie::new();
        trie.insert("apple");
        assert!(trie.search("apple"));
        assert!(!trie.search("app"));
        assert!(trie.starts_with("app"));
    }

    #[test]
    fn prefix_becomes_word_after_insert() {
        let mut trie = Trie::new();
        trie.insert("apple");
        trie.insert("app");
        assert!(trie.search("app"));
        assert!(trie.search("apple"));
    }

    #[test]
    fn missing_words_and_prefixes() {
        let mut trie = Trie::new();
        trie.insert("cat");
        assert!(!trie.search("car"));
        assert!(!trie.starts_with("dog"));
        assert!(trie.starts_with(""));
    }
}
