// Depth-first search (DFS).
//
// Explores a graph by following each branch as deep as possible before
// backtracking. Shown in both the canonical recursive form and an
// iterative form with an explicit stack.
//
// Time:  O(V + E)
// Space: O(V)
package main

import (
	"fmt"
	"reflect"
)

// dfsOrder returns nodes reachable from start in recursive preorder DFS order.
func dfsOrder(graph map[string][]string, start string) []string {
	visited := map[string]bool{}
	order := []string{}
	var visit func(node string)
	visit = func(node string) {
		visited[node] = true
		order = append(order, node)
		for _, neighbor := range graph[node] {
			if !visited[neighbor] {
				visit(neighbor)
			}
		}
	}
	visit(start)
	return order
}

// dfsOrderIterative is DFS with an explicit stack. A node is recorded when
// popped; neighbors are pushed in reverse so the first-listed neighbor is
// explored first, mirroring the recursive variant.
func dfsOrderIterative(graph map[string][]string, start string) []string {
	visited := map[string]bool{start: true}
	order := []string{}
	stack := []string{start}
	for len(stack) > 0 {
		node := stack[len(stack)-1]
		stack = stack[:len(stack)-1]
		order = append(order, node)
		neighbors := graph[node]
		for i := len(neighbors) - 1; i >= 0; i-- {
			neighbor := neighbors[i]
			if !visited[neighbor] {
				visited[neighbor] = true
				stack = append(stack, neighbor)
			}
		}
	}
	return order
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

	expected := []string{"a", "b", "d", "e", "c"}
	if got := dfsOrder(graph, "a"); !reflect.DeepEqual(got, expected) {
		panic(fmt.Sprintf("unexpected recursive order: %v", got))
	}
	if got := dfsOrderIterative(graph, "a"); !reflect.DeepEqual(got, expected) {
		panic(fmt.Sprintf("unexpected iterative order: %v", got))
	}
	if got := dfsOrder(graph, "e"); !reflect.DeepEqual(got, []string{"e"}) {
		panic(fmt.Sprintf("unexpected single-node traversal: %v", got))
	}

	fmt.Println("depth-first-search: all tests passed")
}
