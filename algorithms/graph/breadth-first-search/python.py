"""Breadth-first search (BFS).

Explores a graph outward from a source node, visiting all nodes at
distance k before any node at distance k + 1, using a FIFO queue.
BFS computes shortest paths (fewest edges) in unweighted graphs.

Time:  O(V + E)
Space: O(V)
"""

from collections import deque


def bfs_order(graph: dict[str, list[str]], start: str) -> list[str]:
    """Return the nodes reachable from `start` in BFS visitation order."""
    visited: set[str] = {start}
    order: list[str] = []
    queue: deque[str] = deque([start])
    while queue:
        node = queue.popleft()
        order.append(node)
        for neighbor in graph.get(node, []):
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append(neighbor)
    return order


def bfs_distances(graph: dict[str, list[str]], start: str) -> dict[str, int]:
    """Return the shortest edge-count distance from `start` to each reachable node.

    Unreachable nodes are absent from the result.
    """
    distances: dict[str, int] = {start: 0}
    queue: deque[str] = deque([start])
    while queue:
        node = queue.popleft()
        for neighbor in graph.get(node, []):
            if neighbor not in distances:
                distances[neighbor] = distances[node] + 1
                queue.append(neighbor)
    return distances


if __name__ == "__main__":
    graph = {
        "a": ["b", "c"],
        "b": ["d"],
        "c": ["d"],
        "d": ["e"],
        "e": [],
        "f": ["a"],  # "f" is unreachable from "a"
    }
    assert bfs_order(graph, "a") == ["a", "b", "c", "d", "e"]
    assert bfs_distances(graph, "a") == {"a": 0, "b": 1, "c": 1, "d": 2, "e": 3}
    assert bfs_order(graph, "e") == ["e"]
    print("breadth-first-search: all tests passed")
