// Union-Find (disjoint-set) with path compression and union by rank.
//
// Tracks a partition of {0, ..., n-1} into disjoint sets, supporting Find
// (which set an element belongs to) and Union (merge two sets).
//
// Complexity: O(alpha(n)) amortized per operation, where alpha is the inverse
// Ackermann function (effectively constant). O(n) space.
package main

import "fmt"

// UnionFind is a disjoint-set forest over elements 0..n-1.
type UnionFind struct {
	parent []int
	rank   []int
	count  int // number of disjoint sets
}

// NewUnionFind creates n singleton sets.
func NewUnionFind(n int) *UnionFind {
	parent := make([]int, n)
	for i := range parent {
		parent[i] = i
	}
	return &UnionFind{
		parent: parent,
		rank:   make([]int, n),
		count:  n,
	}
}

// Find returns the representative (root) of the set containing x.
func (uf *UnionFind) Find(x int) int {
	root := x
	for uf.parent[root] != root {
		root = uf.parent[root]
	}
	// Path compression: point every node on the path directly at the root.
	for uf.parent[x] != root {
		uf.parent[x], x = root, uf.parent[x]
	}
	return root
}

// Union merges the sets containing x and y. Returns true if they were separate.
func (uf *UnionFind) Union(x, y int) bool {
	rootX, rootY := uf.Find(x), uf.Find(y)
	if rootX == rootY {
		return false
	}
	// Union by rank: attach the shallower tree under the deeper one.
	if uf.rank[rootX] < uf.rank[rootY] {
		rootX, rootY = rootY, rootX
	}
	uf.parent[rootY] = rootX
	if uf.rank[rootX] == uf.rank[rootY] {
		uf.rank[rootX]++
	}
	uf.count--
	return true
}

// Connected reports whether x and y are in the same set.
func (uf *UnionFind) Connected(x, y int) bool {
	return uf.Find(x) == uf.Find(y)
}

// Count returns the number of disjoint sets.
func (uf *UnionFind) Count() int {
	return uf.count
}

func main() {
	uf := NewUnionFind(10)
	if uf.Count() != 10 {
		panic("expected 10 singleton sets")
	}
	if uf.Connected(0, 1) {
		panic("expected 0 and 1 disconnected")
	}

	if !uf.Union(0, 1) || !uf.Union(1, 2) {
		panic("expected unions of separate sets to return true")
	}
	if uf.Union(0, 2) {
		panic("expected redundant union to return false")
	}
	if !uf.Connected(0, 2) {
		panic("expected 0 and 2 connected")
	}
	if uf.Count() != 8 {
		panic("expected 8 sets")
	}

	uf.Union(3, 4)
	uf.Union(4, 5)
	if uf.Connected(0, 3) {
		panic("expected separate components")
	}
	uf.Union(2, 5)
	if !uf.Connected(0, 3) {
		panic("expected merged components")
	}
	if uf.Count() != 5 {
		panic("expected 5 sets")
	}

	fmt.Println("union-find: all tests passed")
}
