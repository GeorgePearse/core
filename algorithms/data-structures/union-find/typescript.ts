/**
 * Union-Find (disjoint-set) with path compression and union by rank.
 *
 * Tracks a partition of {0, ..., n-1} into disjoint sets, supporting find
 * (which set an element belongs to) and union (merge two sets).
 *
 * Complexity: O(alpha(n)) amortized per operation, where alpha is the inverse
 * Ackermann function (effectively constant). O(n) space.
 */

class UnionFind {
  private parent: number[];
  private rank: number[];
  /** Number of disjoint sets. */
  count: number;

  constructor(n: number) {
    this.parent = Array.from({ length: n }, (_, i) => i);
    this.rank = new Array(n).fill(0);
    this.count = n;
  }

  /** Return the representative (root) of the set containing x. */
  find(x: number): number {
    let root = x;
    while (this.parent[root] !== root) {
      root = this.parent[root];
    }
    // Path compression: point every node on the path directly at the root.
    while (this.parent[x] !== root) {
      const next = this.parent[x];
      this.parent[x] = root;
      x = next;
    }
    return root;
  }

  /** Merge the sets containing x and y. Returns true if they were separate. */
  union(x: number, y: number): boolean {
    let rootX = this.find(x);
    let rootY = this.find(y);
    if (rootX === rootY) {
      return false;
    }
    // Union by rank: attach the shallower tree under the deeper one.
    if (this.rank[rootX] < this.rank[rootY]) {
      [rootX, rootY] = [rootY, rootX];
    }
    this.parent[rootY] = rootX;
    if (this.rank[rootX] === this.rank[rootY]) {
      this.rank[rootX]++;
    }
    this.count--;
    return true;
  }

  /** Return true if x and y are in the same set. */
  connected(x: number, y: number): boolean {
    return this.find(x) === this.find(y);
  }
}

function main(): void {
  const assert = (condition: boolean, message: string): void => {
    if (!condition) {
      throw new Error(`Assertion failed: ${message}`);
    }
  };

  const uf = new UnionFind(10);
  assert(uf.count === 10, "starts with n singleton sets");
  assert(!uf.connected(0, 1), "initially disconnected");

  assert(uf.union(0, 1), "union of separate sets returns true");
  assert(uf.union(1, 2), "union chains");
  assert(!uf.union(0, 2), "redundant union returns false");
  assert(uf.connected(0, 2), "transitively connected");
  assert(uf.count === 8, "count drops per merge");

  assert(uf.union(3, 4), "second component");
  assert(uf.union(4, 5), "second component grows");
  assert(!uf.connected(0, 3), "components separate");
  assert(uf.union(2, 5), "merge components");
  assert(uf.connected(0, 3), "components merged");
  assert(uf.count === 5, "final count");

  console.log("union-find: all tests passed");
}

main();
