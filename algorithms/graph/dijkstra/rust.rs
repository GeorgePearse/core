//! Dijkstra's algorithm.
//!
//! Single-source shortest paths in a weighted graph with non-negative edge
//! weights. Greedily settles the closest unsettled node using a min-heap
//! (`BinaryHeap` with `Reverse`), with lazy deletion of stale heap entries.
//!
//! Time:  O((V + E) log V)
//! Space: O(V)

use std::cmp::Reverse;
use std::collections::{BinaryHeap, HashMap};

/// Adjacency list: node -> [(neighbor, non-negative weight)].
type Graph<'a> = HashMap<&'a str, Vec<(&'a str, u64)>>;

/// Returns the shortest distance from `source` to each reachable node.
/// Unreachable nodes are absent from the result.
fn dijkstra<'a>(graph: &Graph<'a>, source: &'a str) -> HashMap<&'a str, u64> {
    let mut distances: HashMap<&str, u64> = HashMap::from([(source, 0)]);
    let mut heap: BinaryHeap<Reverse<(u64, &str)>> = BinaryHeap::from([Reverse((0, source))]);
    while let Some(Reverse((dist, node))) = heap.pop() {
        if dist > *distances.get(node).unwrap_or(&u64::MAX) {
            continue; // stale entry: a shorter path to `node` was already found
        }
        if let Some(neighbors) = graph.get(node) {
            for &(neighbor, weight) in neighbors {
                let candidate = dist + weight;
                if candidate < *distances.get(neighbor).unwrap_or(&u64::MAX) {
                    distances.insert(neighbor, candidate);
                    heap.push(Reverse((candidate, neighbor)));
                }
            }
        }
    }
    distances
}

fn sample_graph() -> Graph<'static> {
    HashMap::from([
        ("a", vec![("b", 1), ("c", 4)]),
        ("b", vec![("c", 2), ("d", 6)]),
        ("c", vec![("d", 1)]),
        ("d", vec![]),
        ("e", vec![("a", 10)]), // "e" is unreachable from "a"
    ])
}

fn main() {
    let graph = sample_graph();
    let expected: HashMap<&str, u64> = HashMap::from([("a", 0), ("b", 1), ("c", 3), ("d", 4)]);
    assert_eq!(dijkstra(&graph, "a"), expected);
    assert_eq!(dijkstra(&graph, "d"), HashMap::from([("d", 0)]));
    assert_eq!(dijkstra(&graph, "e")["d"], 14);
    println!("dijkstra: all tests passed");
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn finds_shortest_paths() {
        let graph = sample_graph();
        let distances = dijkstra(&graph, "a");
        assert_eq!(distances["d"], 4); // a -> b -> c -> d, not a -> b -> d
        assert!(!distances.contains_key("e"));
    }
}
