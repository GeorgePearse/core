/**
 * Dijkstra's algorithm.
 *
 * Single-source shortest paths in a weighted graph with non-negative edge
 * weights. Greedily settles the closest unsettled node using a binary
 * min-heap, with lazy deletion of stale heap entries.
 *
 * Time:  O((V + E) log V)
 * Space: O(V)
 */

/** Adjacency list: node -> [neighbor, non-negative weight] pairs. */
type WeightedGraph = Map<string, [string, number][]>;

/** Binary min-heap of [distance, node] entries, ordered by distance. */
class MinHeap {
  private items: [number, string][] = [];

  get size(): number {
    return this.items.length;
  }

  push(distance: number, node: string): void {
    this.items.push([distance, node]);
    let child = this.items.length - 1;
    while (child > 0) {
      const parent = (child - 1) >> 1;
      if (this.items[parent][0] <= this.items[child][0]) break;
      [this.items[parent], this.items[child]] = [
        this.items[child],
        this.items[parent],
      ];
      child = parent;
    }
  }

  pop(): [number, string] {
    const top = this.items[0];
    const last = this.items.pop()!;
    if (this.items.length > 0) {
      this.items[0] = last;
      let parent = 0;
      for (;;) {
        let smallest = parent;
        for (const child of [2 * parent + 1, 2 * parent + 2]) {
          if (
            child < this.items.length &&
            this.items[child][0] < this.items[smallest][0]
          ) {
            smallest = child;
          }
        }
        if (smallest === parent) break;
        [this.items[parent], this.items[smallest]] = [
          this.items[smallest],
          this.items[parent],
        ];
        parent = smallest;
      }
    }
    return top;
  }
}

/**
 * Returns the shortest distance from `source` to each reachable node.
 * Unreachable nodes are absent from the result.
 */
function dijkstra(graph: WeightedGraph, source: string): Map<string, number> {
  const distances = new Map<string, number>([[source, 0]]);
  const heap = new MinHeap();
  heap.push(0, source);
  while (heap.size > 0) {
    const [dist, node] = heap.pop();
    if (dist > (distances.get(node) ?? Infinity)) {
      continue; // stale entry: a shorter path to `node` was already found
    }
    for (const [neighbor, weight] of graph.get(node) ?? []) {
      const candidate = dist + weight;
      if (candidate < (distances.get(neighbor) ?? Infinity)) {
        distances.set(neighbor, candidate);
        heap.push(candidate, neighbor);
      }
    }
  }
  return distances;
}

function assert(condition: boolean, message: string): void {
  if (!condition) {
    throw new Error(`assertion failed: ${message}`);
  }
}

function main(): void {
  const graph: WeightedGraph = new Map([
    ["a", [["b", 1], ["c", 4]] as [string, number][]],
    ["b", [["c", 2], ["d", 6]] as [string, number][]],
    ["c", [["d", 1]] as [string, number][]],
    ["d", [] as [string, number][]],
    ["e", [["a", 10]] as [string, number][]], // "e" is unreachable from "a"
  ]);

  const distances = dijkstra(graph, "a");
  assert(distances.get("a") === 0, "distance to a");
  assert(distances.get("b") === 1, "distance to b");
  assert(distances.get("c") === 3, "distance to c (a -> b -> c)");
  assert(distances.get("d") === 4, "distance to d (a -> b -> c -> d)");
  assert(!distances.has("e"), "e is unreachable");

  assert(dijkstra(graph, "d").size === 1, "sink node reaches only itself");
  assert(dijkstra(graph, "e").get("d") === 14, "distance from e to d");

  console.log("dijkstra: all tests passed");
}

main();
