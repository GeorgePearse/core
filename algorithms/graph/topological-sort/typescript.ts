/**
 * Topological sort (Kahn's algorithm).
 *
 * Orders the nodes of a directed acyclic graph so that every edge points
 * from an earlier node to a later one. Repeatedly removes nodes with
 * in-degree zero; if not all nodes can be removed, the graph has a cycle.
 *
 * Convention: returns null when the graph contains a cycle.
 *
 * Time:  O(V + E)
 * Space: O(V)
 */

type Graph = Map<string, string[]>;

/**
 * Returns a topological order of all nodes, or null if a cycle exists.
 *
 * Nodes that appear only as neighbors (with no adjacency entry of their
 * own) are included and treated as having no outgoing edges.
 */
function topologicalSort(graph: Graph): string[] | null {
  const inDegree = new Map<string, number>();
  for (const node of graph.keys()) {
    inDegree.set(node, inDegree.get(node) ?? 0);
  }
  for (const neighbors of graph.values()) {
    for (const neighbor of neighbors) {
      inDegree.set(neighbor, (inDegree.get(neighbor) ?? 0) + 1);
    }
  }

  const queue: string[] = [];
  for (const [node, degree] of inDegree) {
    if (degree === 0) queue.push(node);
  }

  const order: string[] = [];
  let head = 0; // index-based queue head: O(1) dequeue without Array.shift
  while (head < queue.length) {
    const node = queue[head++];
    order.push(node);
    for (const neighbor of graph.get(node) ?? []) {
      const degree = inDegree.get(neighbor)! - 1;
      inDegree.set(neighbor, degree);
      if (degree === 0) queue.push(neighbor);
    }
  }

  if (order.length !== inDegree.size) {
    return null; // a cycle prevented some nodes from reaching in-degree 0
  }
  return order;
}

/** Test helper: order contains every node once and respects every edge. */
function isValidTopologicalOrder(graph: Graph, order: string[]): boolean {
  const allNodes = new Set<string>(graph.keys());
  for (const neighbors of graph.values()) {
    for (const neighbor of neighbors) allNodes.add(neighbor);
  }
  if (order.length !== allNodes.size) return false;

  const position = new Map<string, number>();
  order.forEach((node, index) => position.set(node, index));
  if (position.size !== allNodes.size) return false;

  for (const [node, neighbors] of graph) {
    for (const neighbor of neighbors) {
      if (position.get(node)! >= position.get(neighbor)!) return false;
    }
  }
  return true;
}

function assert(condition: boolean, message: string): void {
  if (!condition) {
    throw new Error(`assertion failed: ${message}`);
  }
}

function main(): void {
  const dag: Graph = new Map([
    ["a", ["b", "c"]],
    ["b", ["d"]],
    ["c", ["d"]],
    ["d", ["e"]],
  ]);
  const order = topologicalSort(dag);
  assert(order !== null, "DAG must have a topological order");
  assert(order!.length === 5, "order includes all five nodes");
  assert(isValidTopologicalOrder(dag, order!), "order respects every edge");

  const cyclic: Graph = new Map([
    ["x", ["y"]],
    ["y", ["z"]],
    ["z", ["x"]],
  ]);
  assert(topologicalSort(cyclic) === null, "cycle is reported as null");

  const empty = topologicalSort(new Map());
  assert(empty !== null && empty.length === 0, "empty graph sorts to []");

  console.log("topological-sort: all tests passed");
}

main();
