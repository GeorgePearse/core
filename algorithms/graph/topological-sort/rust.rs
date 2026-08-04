//! Topological sort (Kahn's algorithm).
//!
//! Orders the nodes of a directed acyclic graph so that every edge points
//! from an earlier node to a later one. Repeatedly removes nodes with
//! in-degree zero; if not all nodes can be removed, the graph has a cycle.
//!
//! Convention: returns `None` when the graph contains a cycle.
//!
//! Time:  O(V + E)
//! Space: O(V)

use std::collections::{HashMap, HashSet, VecDeque};

type Graph<'a> = HashMap<&'a str, Vec<&'a str>>;

/// Returns a topological order of all nodes, or `None` if a cycle exists.
///
/// Nodes that appear only as neighbors (with no adjacency entry of their
/// own) are included and treated as having no outgoing edges.
fn topological_sort<'a>(graph: &Graph<'a>) -> Option<Vec<&'a str>> {
    let mut in_degree: HashMap<&str, usize> = graph.keys().map(|&node| (node, 0)).collect();
    for neighbors in graph.values() {
        for &neighbor in neighbors {
            *in_degree.entry(neighbor).or_insert(0) += 1;
        }
    }

    let mut queue: VecDeque<&str> = in_degree
        .iter()
        .filter(|&(_, &degree)| degree == 0)
        .map(|(&node, _)| node)
        .collect();
    let mut order: Vec<&str> = Vec::with_capacity(in_degree.len());
    while let Some(node) = queue.pop_front() {
        order.push(node);
        if let Some(neighbors) = graph.get(node) {
            for &neighbor in neighbors {
                let degree = in_degree.get_mut(neighbor).expect("known node");
                *degree -= 1;
                if *degree == 0 {
                    queue.push_back(neighbor);
                }
            }
        }
    }

    if order.len() != in_degree.len() {
        return None; // a cycle prevented some nodes from reaching in-degree 0
    }
    Some(order)
}

/// Test helper: checks `order` contains every node exactly once and respects
/// every edge.
fn is_valid_topological_order(graph: &Graph<'_>, order: &[&str]) -> bool {
    let mut all_nodes: HashSet<&str> = graph.keys().copied().collect();
    for neighbors in graph.values() {
        all_nodes.extend(neighbors.iter().copied());
    }

    let position: HashMap<&str, usize> = order
        .iter()
        .enumerate()
        .map(|(index, &node)| (node, index))
        .collect();
    if order.len() != all_nodes.len() || position.len() != all_nodes.len() {
        return false;
    }

    graph.iter().all(|(node, neighbors)| {
        neighbors
            .iter()
            .all(|neighbor| position[node] < position[neighbor])
    })
}

fn main() {
    let dag: Graph = HashMap::from([
        ("a", vec!["b", "c"]),
        ("b", vec!["d"]),
        ("c", vec!["d"]),
        ("d", vec!["e"]),
    ]);
    let order = topological_sort(&dag).expect("DAG must have a topological order");
    assert_eq!(order.len(), 5);
    assert!(is_valid_topological_order(&dag, &order));

    let cyclic: Graph = HashMap::from([("x", vec!["y"]), ("y", vec!["z"]), ("z", vec!["x"])]);
    assert_eq!(topological_sort(&cyclic), None);

    assert_eq!(topological_sort(&Graph::new()), Some(vec![]));
    println!("topological-sort: all tests passed");
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn sorts_dag_and_detects_cycle() {
        let dag: Graph = HashMap::from([("a", vec!["b"]), ("b", vec!["c"]), ("c", vec![])]);
        assert_eq!(topological_sort(&dag), Some(vec!["a", "b", "c"]));

        let cyclic: Graph = HashMap::from([("x", vec!["y"]), ("y", vec!["x"])]);
        assert_eq!(topological_sort(&cyclic), None);
    }
}
