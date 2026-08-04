// Breadth-first search (BFS).
//
// Explores a graph outward from a source node, visiting all nodes at
// distance k before any node at distance k + 1, using a FIFO queue.
// BFS computes shortest paths (fewest edges) in unweighted graphs.
//
// Time:  O(V + E)
// Space: O(V)
package main

import (
	"fmt"
	"reflect"
)

// bfsOrder returns the nodes reachable from start in BFS visitation order.
func bfsOrder(graph map[string][]string, start string) []string {
	visited := map[string]bool{start: true}
	order := []string{}
	queue := []string{start}
	for len(queue) > 0 {
		node := queue[0]
		queue = queue[1:]
		order = append(order, node)
		for _, neighbor := range graph[node] {
			if !visited[neighbor] {
				visited[neighbor] = true
				queue = append(queue, neighbor)
			}
		}
	}
	return order
}

// bfsDistances returns the shortest edge-count distance from start to each
// reachable node. Unreachable nodes are absent from the result.
func bfsDistances(graph map[string][]string, start string) map[string]int {
	distances := map[string]int{start: 0}
	queue := []string{start}
	for len(queue) > 0 {
		node := queue[0]
		queue = queue[1:]
		for _, neighbor := range graph[node] {
			if _, seen := distances[neighbor]; !seen {
				distances[neighbor] = distances[node] + 1
				queue = append(queue, neighbor)
			}
		}
	}
	return distances
}

func main() {
	graph := map[string][]string{
		"a": {"b", "c"},
		"b": {"d"},
		"c": {"d"},
		"d": {"e"},
		"e": {},
		"f": {"a"}, // "f" is unreachable from "a"
	}

	order := bfsOrder(graph, "a")
	if !reflect.DeepEqual(order, []string{"a", "b", "c", "d", "e"}) {
		panic(fmt.Sprintf("unexpected visitation order: %v", order))
	}

	distances := bfsDistances(graph, "a")
	expected := map[string]int{"a": 0, "b": 1, "c": 1, "d": 2, "e": 3}
	if !reflect.DeepEqual(distances, expected) {
		panic(fmt.Sprintf("unexpected distances: %v", distances))
	}

	if !reflect.DeepEqual(bfsOrder(graph, "e"), []string{"e"}) {
		panic("single-node traversal failed")
	}

	fmt.Println("breadth-first-search: all tests passed")
}
