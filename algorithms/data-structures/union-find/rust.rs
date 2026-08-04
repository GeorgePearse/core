//! Union-Find (disjoint-set) with path compression and union by rank.
//!
//! Tracks a partition of {0, ..., n-1} into disjoint sets, supporting `find`
//! (which set an element belongs to) and `union` (merge two sets).
//!
//! Complexity: O(alpha(n)) amortized per operation, where alpha is the inverse
//! Ackermann function (effectively constant). O(n) space.

/// Disjoint-set forest over elements `0..n`.
pub struct UnionFind {
    parent: Vec<usize>,
    rank: Vec<u8>,
    /// Number of disjoint sets.
    count: usize,
}

impl UnionFind {
    pub fn new(n: usize) -> Self {
        UnionFind {
            parent: (0..n).collect(),
            rank: vec![0; n],
            count: n,
        }
    }

    /// Return the representative (root) of the set containing `x`.
    pub fn find(&mut self, x: usize) -> usize {
        let mut root = x;
        while self.parent[root] != root {
            root = self.parent[root];
        }
        // Path compression: point every node on the path directly at the root.
        let mut node = x;
        while self.parent[node] != root {
            let next = self.parent[node];
            self.parent[node] = root;
            node = next;
        }
        root
    }

    /// Merge the sets containing `x` and `y`. Returns `true` if they were separate.
    pub fn union(&mut self, x: usize, y: usize) -> bool {
        let (mut root_x, mut root_y) = (self.find(x), self.find(y));
        if root_x == root_y {
            return false;
        }
        // Union by rank: attach the shallower tree under the deeper one.
        if self.rank[root_x] < self.rank[root_y] {
            std::mem::swap(&mut root_x, &mut root_y);
        }
        self.parent[root_y] = root_x;
        if self.rank[root_x] == self.rank[root_y] {
            self.rank[root_x] += 1;
        }
        self.count -= 1;
        true
    }

    /// Return `true` if `x` and `y` are in the same set.
    pub fn connected(&mut self, x: usize, y: usize) -> bool {
        self.find(x) == self.find(y)
    }

    /// Number of disjoint sets.
    pub fn count(&self) -> usize {
        self.count
    }
}

fn main() {
    let mut uf = UnionFind::new(10);
    assert_eq!(uf.count(), 10);
    assert!(!uf.connected(0, 1));

    assert!(uf.union(0, 1));
    assert!(uf.union(1, 2));
    assert!(!uf.union(0, 2)); // already connected
    assert!(uf.connected(0, 2));
    assert_eq!(uf.count(), 8);

    assert!(uf.union(3, 4));
    assert!(uf.union(4, 5));
    assert!(!uf.connected(0, 3));
    assert!(uf.union(2, 5));
    assert!(uf.connected(0, 3));
    assert_eq!(uf.count(), 5);

    println!("union-find: all tests passed");
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn union_and_find() {
        let mut uf = UnionFind::new(5);
        assert!(uf.union(0, 1));
        assert!(uf.union(2, 3));
        assert!(!uf.connected(0, 2));
        assert!(uf.union(1, 3));
        assert!(uf.connected(0, 2));
        assert_eq!(uf.count(), 2);
    }

    #[test]
    fn redundant_union_returns_false() {
        let mut uf = UnionFind::new(3);
        assert!(uf.union(0, 1));
        assert!(!uf.union(1, 0));
        assert_eq!(uf.count(), 2);
    }
}
