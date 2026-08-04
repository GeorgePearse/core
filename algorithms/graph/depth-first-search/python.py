"""Depth-first search (DFS).

Explores a graph by following each branch as deep as possible before
backtracking. Shown in both the canonical recursive form and an
iterative form with an explicit stack.

Time:  O(V + E)
Space: O(V)
"""


def dfs_order(graph: dict[str, list[str]], start: str) -> list[str]:
    """Return nodes reachable from `start` in recursive preorder DFS order."""
    visited: set[str] = set()
    order: list[str] = []

    def visit(node: str) -> None:
        visited.add(node)
        order.append(node)
        for neighbor in graph.get(node, []):
            if neighbor not in visited:
                visit(neighbor)

    visit(start)
    return order


def dfs_order_iterative(graph: dict[str, list[str]], start: str) -> list[str]:
    """Iterative DFS using an explicit stack.

    A node is recorded when popped; neighbors are pushed in reverse so the
    first-listed neighbor is explored first, mirroring the recursive variant.
    """
    visited: set[str] = {start}
    order: list[str] = []
    stack: list[str] = [start]
    while stack:
        node = stack.pop()
        order.append(node)
        for neighbor in reversed(graph.get(node, [])):
            if neighbor not in visited:
                visited.add(neighbor)
                stack.append(neighbor)
    return order


if __name__ == "__main__":
    graph = {
        "a": ["b", "c"],
        "b": ["d"],
        "c": ["d"],
        "d": ["e"],
        "e": [],
        "f": ["a"],  # "f" is unreachable from "a"
    }
    assert dfs_order(graph, "a") == ["a", "b", "d", "e", "c"]
    assert dfs_order_iterative(graph, "a") == ["a", "b", "d", "e", "c"]
    assert dfs_order(graph, "e") == ["e"]
    print("depth-first-search: all tests passed")
