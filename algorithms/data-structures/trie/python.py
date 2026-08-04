"""Trie (prefix tree) over lowercase words.

Supports insert, exact-word search, and prefix search (starts_with), each in
time proportional to the length of the word or prefix.

Complexity: O(m) per operation where m is the word length;
O(total characters stored) space.
"""

from __future__ import annotations


class TrieNode:
    """A single trie node: children keyed by character, plus an end-of-word flag."""

    __slots__ = ("children", "is_end_of_word")

    def __init__(self) -> None:
        self.children: dict[str, TrieNode] = {}
        self.is_end_of_word: bool = False


class Trie:
    """Prefix tree over lowercase words."""

    def __init__(self) -> None:
        self.root = TrieNode()

    def insert(self, word: str) -> None:
        """Add word to the trie."""
        node = self.root
        for char in word:
            if char not in node.children:
                node.children[char] = TrieNode()
            node = node.children[char]
        node.is_end_of_word = True

    def search(self, word: str) -> bool:
        """Return True if word was previously inserted as a complete word."""
        node = self._walk(word)
        return node is not None and node.is_end_of_word

    def starts_with(self, prefix: str) -> bool:
        """Return True if any inserted word starts with prefix."""
        return self._walk(prefix) is not None

    def _walk(self, key: str) -> TrieNode | None:
        """Follow key character by character; return the final node or None."""
        node = self.root
        for char in key:
            if char not in node.children:
                return None
            node = node.children[char]
        return node


if __name__ == "__main__":
    trie = Trie()
    trie.insert("apple")
    assert trie.search("apple")
    assert not trie.search("app")  # prefix only, not a full word
    assert trie.starts_with("app")
    assert not trie.starts_with("banana")

    trie.insert("app")
    assert trie.search("app")

    trie.insert("application")
    assert trie.search("application")
    assert trie.starts_with("appl")
    assert not trie.search("appl")
    assert trie.starts_with("")  # empty prefix matches everything

    print("trie: all tests passed")
