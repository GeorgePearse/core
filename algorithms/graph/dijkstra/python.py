"""Dijkstra's algorithm.

Single-source shortest paths in a weighted graph with non-negative edge
weights. Greedily settles the closest unsettled node using a min-heap,
with lazy deletion of stale heap entries.

Time:  O((V + E) log V)
Space: O(V)
"""

import heapq
from math import inf


def dijkstra(
    graph: dict[str, list[tuple[str, float]]], source: str
) -> dict[str, float]:
    """Return the shortest distance from `source` to each reachable node.

    `graph` maps each node to a list of (neighbor, weight) pairs; weights
    must be non-negative. Unreachable nodes are absent from the result.
    """
    distances: dict[str, float] = {source: 0.0}
    heap: list[tuple[float, str]] = [(0.0, source)]
    while heap:
        dist, node = heapq.heappop(heap)
        if dist > distances.get(node, inf):
            continue  # stale entry: a shorter path to `node` was already found
        for neighbor, weight in graph.get(node, []):
            candidate = dist + weight
            if candidate < distances.get(neighbor, inf):
                distances[neighbor] = candidate
                heapq.heappush(heap, (candidate, neighbor))
    return distances


if __name__ == "__main__":
    graph = {
        "a": [("b", 1.0), ("c", 4.0)],
        "b": [("c", 2.0), ("d", 6.0)],
        "c": [("d", 1.0)],
        "d": [],
        "e": [("a", 10.0)],  # "e" is unreachable from "a"
    }
    assert dijkstra(graph, "a") == {"a": 0.0, "b": 1.0, "c": 3.0, "d": 4.0}
    assert dijkstra(graph, "d") == {"d": 0.0}
    assert dijkstra(graph, "e")["d"] == 14.0
    print("dijkstra: all tests passed")
