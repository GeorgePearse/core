// Topological sort (Kahn's algorithm).
//
// Orders the nodes of a directed acyclic graph so that every edge points
// from an earlier node to a later one. Repeatedly removes nodes with
// in-degree zero; if not all nodes can be removed, the graph has a cycle.
//
// Convention: returns a non-nil error when the graph contains a cycle.
//
// Time:  O(V + E)
// Space: O(V)
package main

import (
	"errors"
	"fmt"
)

// topologicalSort returns a topological order of all nodes, or an error if
// a cycle exists. Nodes that appear only as neighbors (with no adjacency
// entry of their own) are included and treated as having no outgoing edges.
func topologicalSort(graph map[string][]string) ([]string, error) {
	inDegree := map[string]int{}
	for node, neighbors := range graph {
		if _, seen := inDegree[node]; !seen {
			inDegree[node] = 0
		}
		for _, neighbor := range neighbors {
			inDegree[neighbor]++
		}
	}

	queue := []string{}
	for node, degree := range inDegree {
		if degree == 0 {
			queue = append(queue, node)
		}
	}

	order := make([]string, 0, len(inDegree))
	for len(queue) > 0 {
		node := queue[0]
		queue = queue[1:]
		order = append(order, node)
		for _, neighbor := range graph[node] {
			inDegree[neighbor]--
			if inDegree[neighbor] == 0 {
				queue = append(queue, neighbor)
			}
		}
	}

	if len(order) != len(inDegree) {
		// A cycle prevented some nodes from reaching in-degree 0.
		return nil, errors.New("graph contains a cycle")
	}
	return order, nil
}

// isValidTopologicalOrder is a test helper: order contains every node once
// and respects every edge.
func isValidTopologicalOrder(graph map[string][]string, order []string) bool {
	allNodes := map[string]bool{}
	for node, neighbors := range graph {
		allNodes[node] = true
		for _, neighbor := range neighbors {
			allNodes[neighbor] = true
		}
	}
	if len(order) != len(allNodes) {
		return false
	}

	position := map[string]int{}
	for index, node := range order {
		position[node] = index
	}
	if len(position) != len(allNodes) {
		return false
	}

	for node, neighbors := range graph {
		for _, neighbor := range neighbors {
			if position[node] >= position[neighbor] {
				return false
			}
		}
	}
	return true
}

func main() {
	dag := map[string][]string{
		"a": {"b", "c"},
		"b": {"d"},
		"c": {"d"},
		"d": {"e"},
	}
	order, err := topologicalSort(dag)
	if err != nil {
		panic(fmt.Sprintf("DAG must have a topological order: %v", err))
	}
	if len(order) != 5 || !isValidTopologicalOrder(dag, order) {
		panic(fmt.Sprintf("invalid topological order: %v", order))
	}

	cyclic := map[string][]string{"x": {"y"}, "y": {"z"}, "z": {"x"}}
	if _, err := topologicalSort(cyclic); err == nil {
		panic("cycle was not detected")
	}

	empty, err := topologicalSort(map[string][]string{})
	if err != nil || len(empty) != 0 {
		panic("empty graph should sort to an empty order")
	}

	fmt.Println("topological-sort: all tests passed")
}
