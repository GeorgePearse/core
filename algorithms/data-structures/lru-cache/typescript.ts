/**
 * LRU (least recently used) cache.
 *
 * Fixed-capacity key-value cache that evicts the least recently used entry
 * when full. Uses a hash map from key to list node plus a doubly linked list
 * with sentinel head/tail nodes, ordered from most recently used (front) to
 * least recently used (back).
 *
 * Complexity: O(1) per get/put, O(capacity) space.
 */

class LruNode {
  key: number;
  value: number;
  prev: LruNode | null = null;
  next: LruNode | null = null;

  constructor(key: number, value: number) {
    this.key = key;
    this.value = value;
  }
}

class LRUCache {
  private readonly capacity: number;
  private readonly map: Map<number, LruNode> = new Map();
  private readonly head: LruNode; // sentinel; head.next is most recently used
  private readonly tail: LruNode; // sentinel; tail.prev is least recently used

  constructor(capacity: number) {
    if (capacity <= 0) {
      throw new Error("capacity must be positive");
    }
    this.capacity = capacity;
    this.head = new LruNode(0, 0);
    this.tail = new LruNode(0, 0);
    this.head.next = this.tail;
    this.tail.prev = this.head;
  }

  /** Return the value for key, marking it most recently used. -1 if absent. */
  get(key: number): number {
    const node = this.map.get(key);
    if (node === undefined) {
      return -1;
    }
    this.detach(node);
    this.pushFront(node);
    return node.value;
  }

  /** Insert or update key, evicting the least recently used entry if full. */
  put(key: number, value: number): void {
    const existing = this.map.get(key);
    if (existing !== undefined) {
      existing.value = value;
      this.detach(existing);
      this.pushFront(existing);
      return;
    }

    if (this.map.size === this.capacity) {
      const lru = this.tail.prev!; // least recently used (never a sentinel here)
      this.detach(lru);
      this.map.delete(lru.key);
    }

    const node = new LruNode(key, value);
    this.map.set(key, node);
    this.pushFront(node);
  }

  get size(): number {
    return this.map.size;
  }

  /** Unlink a node from the recency list. */
  private detach(node: LruNode): void {
    node.prev!.next = node.next;
    node.next!.prev = node.prev;
    node.prev = null;
    node.next = null;
  }

  /** Insert a node right after the head sentinel (most recently used). */
  private pushFront(node: LruNode): void {
    node.prev = this.head;
    node.next = this.head.next;
    this.head.next!.prev = node;
    this.head.next = node;
  }
}

function main(): void {
  const assert = (condition: boolean, message: string): void => {
    if (!condition) {
      throw new Error(`Assertion failed: ${message}`);
    }
  };

  const cache = new LRUCache(2);
  cache.put(1, 1);
  cache.put(2, 2);
  assert(cache.get(1) === 1, "get returns stored value"); // 1 is now MRU
  cache.put(3, 3); // evicts key 2
  assert(cache.get(2) === -1, "least recently used key evicted");
  assert(cache.get(3) === 3, "new key present");
  cache.put(1, 10); // update existing key
  assert(cache.get(1) === 10, "update overwrites value");
  cache.put(4, 4); // evicts key 3 (1 was refreshed by the update)
  assert(cache.get(3) === -1, "key 3 evicted");
  assert(cache.get(1) === 10, "key 1 retained");
  assert(cache.get(4) === 4, "key 4 present");
  assert(cache.size === 2, "size capped at capacity");
  console.log("lru-cache: all tests passed");
}

main();
