//! Depth-first search (DFS).
//!
//! Explores a graph by following each branch as deep as possible before
//! backtracking. Shown in both the canonical recursive form and an
//! iterative form with an explicit stack.
//!
//! Time:  O(V + E)
//! Space: O(V)

use std::collections::{HashMap, HashSet};

type Graph<'a> = HashMap<&'a str, Vec<&'a str>>;

/// Returns nodes reachable from `start` in recursive preorder DFS order.
fn dfs_order<'a>(graph: &Graph<'a>, start: &'a str) -> Vec<&'a str> {
    let mut visited: HashSet<&str> = HashSet::new();
    let mut order: Vec<&str> = Vec::new();
    visit(graph, start, &mut visited, &mut order);
    order
}

fn visit<'a>(
    graph: &Graph<'a>,
    node: &'a str,
    visited: &mut HashSet<&'a str>,
    order: &mut Vec<&'a str>,
) {
    visited.insert(node);
    order.push(node);
    if let Some(neighbors) = graph.get(node) {
        for &neighbor in neighbors {
            if !visited.contains(neighbor) {
                visit(graph, neighbor, visited, order);
            }
        }
    }
}

/// Iterative DFS using an explicit stack.
///
/// A node is recorded when popped; neighbors are pushed in reverse so the
/// first-listed neighbor is explored first, mirroring the recursive variant.
fn dfs_order_iterative<'a>(graph: &Graph<'a>, start: &'a str) -> Vec<&'a str> {
    let mut visited: HashSet<&str> = HashSet::from([start]);
    let mut order: Vec<&str> = Vec::new();
    let mut stack: Vec<&str> = vec![start];
    while let Some(node) = stack.pop() {
        order.push(node);
        if let Some(neighbors) = graph.get(node) {
            for &neighbor in neighbors.iter().rev() {
                if visited.insert(neighbor) {
                    stack.push(neighbor);
                }
            }
        }
    }
    order
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
    assert_eq!(dfs_order(&graph, "a"), vec!["a", "b", "d", "e", "c"]);
    assert_eq!(dfs_order_iterative(&graph, "a"), vec!["a", "b", "d", "e", "c"]);
    assert_eq!(dfs_order(&graph, "e"), vec!["e"]);
    println!("depth-first-search: all tests passed");
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn recursive_and_iterative_agree() {
        let graph = sample_graph();
        assert_eq!(dfs_order(&graph, "a"), vec!["a", "b", "d", "e", "c"]);
        assert_eq!(dfs_order(&graph, "a"), dfs_order_iterative(&graph, "a"));
    }
}
