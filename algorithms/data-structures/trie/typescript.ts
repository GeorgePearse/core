/**
 * Trie (prefix tree) over lowercase words.
 *
 * Supports insert, exact-word search, and prefix search (startsWith), each in
 * time proportional to the length of the word or prefix. Children are stored
 * in a Map keyed by character.
 *
 * Complexity: O(m) per operation where m is the word length;
 * O(total characters stored) space.
 */

class TrieNode {
  readonly children: Map<string, TrieNode> = new Map();
  isEndOfWord = false;
}

class Trie {
  private readonly root: TrieNode = new TrieNode();

  /** Add a word (lowercase a-z) to the trie. */
  insert(word: string): void {
    let node = this.root;
    for (const char of word) {
      let child = node.children.get(char);
      if (child === undefined) {
        child = new TrieNode();
        node.children.set(char, child);
      }
      node = child;
    }
    node.isEndOfWord = true;
  }

  /** Return true if the word was previously inserted as a complete word. */
  search(word: string): boolean {
    const node = this.walk(word);
    return node !== null && node.isEndOfWord;
  }

  /** Return true if any inserted word starts with the prefix. */
  startsWith(prefix: string): boolean {
    return this.walk(prefix) !== null;
  }

  /** Follow the key character by character; return the final node or null. */
  private walk(key: string): TrieNode | null {
    let node = this.root;
    for (const char of key) {
      const child = node.children.get(char);
      if (child === undefined) {
        return null;
      }
      node = child;
    }
    return node;
  }
}

function main(): void {
  const assert = (condition: boolean, message: string): void => {
    if (!condition) {
      throw new Error(`Assertion failed: ${message}`);
    }
  };

  const trie = new Trie();
  trie.insert("apple");
  assert(trie.search("apple"), "finds inserted word");
  assert(!trie.search("app"), "prefix alone is not a word");
  assert(trie.startsWith("app"), "prefix is present");
  assert(!trie.startsWith("banana"), "absent prefix");

  trie.insert("app");
  assert(trie.search("app"), "prefix becomes a word after insert");

  trie.insert("application");
  assert(trie.search("application"), "finds longer word");
  assert(trie.startsWith("appl"), "shared prefix present");
  assert(!trie.search("appl"), "internal node is not a word");
  assert(trie.startsWith(""), "empty prefix matches everything");

  console.log("trie: all tests passed");
}

main();
