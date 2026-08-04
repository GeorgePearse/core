// Trie (prefix tree) over lowercase words.
//
// Supports Insert, exact-word Search, and prefix search (StartsWith), each in
// time proportional to the length of the word or prefix. Children are stored
// in a fixed 26-slot array indexed by letter - 'a'.
//
// Complexity: O(m) per operation where m is the word length;
// O(total characters stored) space.
package main

import "fmt"

const alphabetSize = 26

type trieNode struct {
	children    [alphabetSize]*trieNode
	isEndOfWord bool
}

// Trie is a prefix tree over lowercase words.
type Trie struct {
	root *trieNode
}

// NewTrie creates an empty trie.
func NewTrie() *Trie {
	return &Trie{root: &trieNode{}}
}

// Insert adds a word (lowercase a-z) to the trie.
func (t *Trie) Insert(word string) {
	node := t.root
	for i := 0; i < len(word); i++ {
		index := word[i] - 'a'
		if node.children[index] == nil {
			node.children[index] = &trieNode{}
		}
		node = node.children[index]
	}
	node.isEndOfWord = true
}

// Search reports whether word was previously inserted as a complete word.
func (t *Trie) Search(word string) bool {
	node := t.walk(word)
	return node != nil && node.isEndOfWord
}

// StartsWith reports whether any inserted word starts with prefix.
func (t *Trie) StartsWith(prefix string) bool {
	return t.walk(prefix) != nil
}

// walk follows key character by character; returns the final node or nil.
func (t *Trie) walk(key string) *trieNode {
	node := t.root
	for i := 0; i < len(key); i++ {
		index := key[i] - 'a'
		if node.children[index] == nil {
			return nil
		}
		node = node.children[index]
	}
	return node
}

func main() {
	trie := NewTrie()
	trie.Insert("apple")
	if !trie.Search("apple") {
		panic("expected to find inserted word")
	}
	if trie.Search("app") { // prefix only, not a full word
		panic("expected prefix alone not to be a word")
	}
	if !trie.StartsWith("app") {
		panic("expected prefix to be present")
	}
	if trie.StartsWith("banana") {
		panic("expected absent prefix")
	}

	trie.Insert("app")
	if !trie.Search("app") {
		panic("expected prefix to become a word after insert")
	}

	trie.Insert("application")
	if !trie.Search("application") {
		panic("expected to find longer word")
	}
	if !trie.StartsWith("appl") {
		panic("expected shared prefix to be present")
	}
	if trie.Search("appl") {
		panic("expected internal node not to be a word")
	}
	if !trie.StartsWith("") { // empty prefix matches everything
		panic("expected empty prefix to match")
	}

	fmt.Println("trie: all tests passed")
}
