//! Breadth-first search (BFS).
//!
//! Explores a graph outward from a source node, visiting all nodes at
//! distance k before any node at distance k + 1, using a FIFO queue.
//! BFS computes shortest paths (fewest edges) in unweighted graphs.
//!
//! Time:  O(V + E)
//! Space: O(V)

use std::collections::{HashMap, HashSet, VecDeque};

type Graph<'a> = HashMap<&'a str, Vec<&'a str>>;

/// Returns the nodes reachable from `start` in BFS visitation order.
fn bfs_order<'a>(graph: &Graph<'a>, start: &'a str) -> Vec<&'a str> {
    let mut visited: HashSet<&str> = HashSet::from([start]);
    let mut order: Vec<&str> = Vec::new();
    let mut queue: VecDeque<&str> = VecDeque::from([start]);
    while let Some(node) = queue.pop_front() {
        order.push(node);
        if let Some(neighbors) = graph.get(node) {
            for &neighbor in neighbors {
                if visited.insert(neighbor) {
                    queue.push_back(neighbor);
                }
            }
        }
    }
    order
}

/// Returns the shortest edge-count distance from `start` to each reachable
/// node. Unreachable nodes are absent from the result.
fn bfs_distances<'a>(graph: &Graph<'a>, start: &'a str) -> HashMap<&'a str, usize> {
    let mut distances: HashMap<&str, usize> = HashMap::from([(start, 0)]);
    let mut queue: VecDeque<&str> = VecDeque::from([start]);
    while let Some(node) = queue.pop_front() {
        let dist = distances[node];
        if let Some(neighbors) = graph.get(node) {
            for &neighbor in neighbors {
                if !distances.contains_key(neighbor) {
                    distances.insert(neighbor, dist + 1);
                    queue.push_back(neighbor);
                }
            }
        }
    }
    distances
}

fn sample_graph() -> Graph<'static> {
    HashMap::from([
        ("a", vec!["b", "c"]),
        ("b", vec!["d"]),
        ("c", vec!["d"]),
        ("d", vec!["e"]),
        ("e", vec![]),
        ("f", vec!["a"]), // "f" is unreachable from "a"
    ])
}

fn main() {
    let graph = sample_graph();
    assert_eq!(bfs_order(&graph, "a"), vec!["a", "b", "c", "d", "e"]);
    let expected: HashMap<&str, usize> =
        HashMap::from([("a", 0), ("b", 1), ("c", 1), ("d", 2), ("e", 3)]);
    assert_eq!(bfs_distances(&graph, "a"), expected);
    assert_eq!(bfs_order(&graph, "e"), vec!["e"]);
    println!("breadth-first-search: all tests passed");
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn bfs_visits_in_level_order_and_computes_distances() {
        let graph = sample_graph();
        assert_eq!(bfs_order(&graph, "a"), vec!["a", "b", "c", "d", "e"]);
        assert_eq!(bfs_distances(&graph, "a")["e"], 3);
        assert!(!bfs_distances(&graph, "a").contains_key("f"));
    }
}
