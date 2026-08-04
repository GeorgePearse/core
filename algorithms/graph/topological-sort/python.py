"""Topological sort (Kahn's algorithm).

Orders the nodes of a directed acyclic graph so that every edge points
from an earlier node to a later one. Repeatedly removes nodes with
in-degree zero; if not all nodes can be removed, the graph has a cycle.

Convention: returns None when the graph contains a cycle.

Time:  O(V + E)
Space: O(V)
"""

from collections import deque


def topological_sort(graph: dict[str, list[str]]) -> list[str] | None:
    """Return a topological order of all nodes, or None if a cycle exists.

    Nodes that appear only as neighbors (with no adjacency entry of their
    own) are included and treated as having no outgoing edges.
    """
    in_degree: dict[str, int] = {node: 0 for node in graph}
    for neighbors in graph.values():
        for neighbor in neighbors:
            in_degree[neighbor] = in_degree.get(neighbor, 0) + 1

    queue: deque[str] = deque(node for node, deg in in_degree.items() if deg == 0)
    order: list[str] = []
    while queue:
        node = queue.popleft()
        order.append(node)
        for neighbor in graph.get(node, []):
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if len(order) != len(in_degree):
        return None  # a cycle prevented some nodes from reaching in-degree 0
    return order


def _is_valid_topological_order(
    graph: dict[str, list[str]], order: list[str]
) -> bool:
    all_nodes = set(graph) | {n for neighbors in graph.values() for n in neighbors}
    if len(order) != len(all_nodes) or set(order) != all_nodes:
        return False
    position = {node: index for index, node in enumerate(order)}
    return all(
        position[node] < position[neighbor]
        for node, neighbors in graph.items()
        for neighbor in neighbors
    )


if __name__ == "__main__":
    dag = {
        "a": ["b", "c"],
        "b": ["d"],
        "c": ["d"],
        "d": ["e"],
    }
    order = topological_sort(dag)
    assert order is not None
    assert _is_valid_topological_order(dag, order)

    cyclic = {"x": ["y"], "y": ["z"], "z": ["x"]}
    assert topological_sort(cyclic) is None

    assert topological_sort({}) == []
    print("topological-sort: all tests passed")
