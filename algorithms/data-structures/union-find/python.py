"""Union-Find (disjoint-set) with path compression and union by rank.

Tracks a partition of {0, ..., n-1} into disjoint sets, supporting `find`
(which set an element belongs to) and `union` (merge two sets).

Complexity: O(alpha(n)) amortized per operation, where alpha is the inverse
Ackermann function (effectively constant). O(n) space.
"""

from __future__ import annotations


class UnionFind:
    """Disjoint-set forest over elements 0..n-1."""

    def __init__(self, n: int) -> None:
        self.parent: list[int] = list(range(n))
        self.rank: list[int] = [0] * n
        self.count: int = n  # number of disjoint sets

    def find(self, x: int) -> int:
        """Return the representative (root) of the set containing x."""
        root = x
        while self.parent[root] != root:
            root = self.parent[root]
        # Path compression: point every node on the path directly at the root.
        while self.parent[x] != root:
            self.parent[x], x = root, self.parent[x]
        return root

    def union(self, x: int, y: int) -> bool:
        """Merge the sets containing x and y. Return True if they were separate."""
        root_x, root_y = self.find(x), self.find(y)
        if root_x == root_y:
            return False
        # Union by rank: attach the shallower tree under the deeper one.
        if self.rank[root_x] < self.rank[root_y]:
            root_x, root_y = root_y, root_x
        self.parent[root_y] = root_x
        if self.rank[root_x] == self.rank[root_y]:
            self.rank[root_x] += 1
        self.count -= 1
        return True

    def connected(self, x: int, y: int) -> bool:
        """Return True if x and y are in the same set."""
        return self.find(x) == self.find(y)


if __name__ == "__main__":
    uf = UnionFind(10)
    assert uf.count == 10
    assert not uf.connected(0, 1)

    assert uf.union(0, 1)
    assert uf.union(1, 2)
    assert not uf.union(0, 2)  # already connected
    assert uf.connected(0, 2)
    assert uf.count == 8

    assert uf.union(3, 4)
    assert uf.union(4, 5)
    assert not uf.connected(0, 3)
    assert uf.union(2, 5)
    assert uf.connected(0, 3)
    assert uf.count == 5

    print("union-find: all tests passed")
