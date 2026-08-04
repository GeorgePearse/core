/**
 * Breadth-first search (BFS).
 *
 * Explores a graph outward from a source node, visiting all nodes at
 * distance k before any node at distance k + 1, using a FIFO queue.
 * BFS computes shortest paths (fewest edges) in unweighted graphs.
 *
 * Time:  O(V + E)
 * Space: O(V)
 */

type Graph = Map<string, string[]>;

/** Returns the nodes reachable from `start` in BFS visitation order. */
function bfsOrder(graph: Graph, start: string): string[] {
  const visited = new Set<string>([start]);
  const order: string[] = [];
  const queue: string[] = [start];
  let head = 0; // index-based queue head: O(1) dequeue without Array.shift
  while (head < queue.length) {
    const node = queue[head++];
    order.push(node);
    for (const neighbor of graph.get(node) ?? []) {
      if (!visited.has(neighbor)) {
        visited.add(neighbor);
        queue.push(neighbor);
      }
    }
  }
  return order;
}

/**
 * Returns the shortest edge-count distance from `start` to each reachable
 * node. Unreachable nodes are absent from the result.
 */
function bfsDistances(graph: Graph, start: string): Map<string, number> {
  const distances = new Map<string, number>([[start, 0]]);
  const queue: string[] = [start];
  let head = 0;
  while (head < queue.length) {
    const node = queue[head++];
    const dist = distances.get(node)!;
    for (const neighbor of graph.get(node) ?? []) {
      if (!distances.has(neighbor)) {
        distances.set(neighbor, dist + 1);
        queue.push(neighbor);
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
  const graph: Graph = new Map([
    ["a", ["b", "c"]],
    ["b", ["d"]],
    ["c", ["d"]],
    ["d", ["e"]],
    ["e", []],
    ["f", ["a"]], // "f" is unreachable from "a"
  ]);

  assert(bfsOrder(graph, "a").join(",") === "a,b,c,d,e", "visitation order");

  const distances = bfsDistances(graph, "a");
  assert(distances.get("a") === 0, "distance to a");
  assert(distances.get("b") === 1, "distance to b");
  assert(distances.get("c") === 1, "distance to c");
  assert(distances.get("d") === 2, "distance to d");
  assert(distances.get("e") === 3, "distance to e");
  assert(!distances.has("f"), "f is unreachable");

  assert(bfsOrder(graph, "e").join(",") === "e", "single-node traversal");

  console.log("breadth-first-search: all tests passed");
}

main();
