/**
 * Depth-first search (DFS).
 *
 * Explores a graph by following each branch as deep as possible before
 * backtracking. Shown in both the canonical recursive form and an
 * iterative form with an explicit stack.
 *
 * Time:  O(V + E)
 * Space: O(V)
 */

type Graph = Map<string, string[]>;

/** Returns nodes reachable from `start` in recursive preorder DFS order. */
function dfsOrder(graph: Graph, start: string): string[] {
  const visited = new Set<string>();
  const order: string[] = [];

  function visit(node: string): void {
    visited.add(node);
    order.push(node);
    for (const neighbor of graph.get(node) ?? []) {
      if (!visited.has(neighbor)) {
        visit(neighbor);
      }
    }
  }

  visit(start);
  return order;
}

/**
 * Iterative DFS using an explicit stack.
 *
 * A node is recorded when popped; neighbors are pushed in reverse so the
 * first-listed neighbor is explored first, mirroring the recursive variant.
 */
function dfsOrderIterative(graph: Graph, start: string): string[] {
  const visited = new Set<string>([start]);
  const order: string[] = [];
  const stack: string[] = [start];
  while (stack.length > 0) {
    const node = stack.pop()!;
    order.push(node);
    const neighbors = graph.get(node) ?? [];
    for (let i = neighbors.length - 1; i >= 0; i--) {
      const neighbor = neighbors[i];
      if (!visited.has(neighbor)) {
        visited.add(neighbor);
        stack.push(neighbor);
      }
    }
  }
  return order;
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

  assert(dfsOrder(graph, "a").join(",") === "a,b,d,e,c", "recursive order");
  assert(
    dfsOrderIterative(graph, "a").join(",") === "a,b,d,e,c",
    "iterative order",
  );
  assert(dfsOrder(graph, "e").join(",") === "e", "single-node traversal");

  console.log("depth-first-search: all tests passed");
}

main();
