// Dijkstra's algorithm.
//
// Single-source shortest paths in a weighted graph with non-negative edge
// weights. Greedily settles the closest unsettled node using a min-heap
// (container/heap), with lazy deletion of stale heap entries.
//
// Time:  O((V + E) log V)
// Space: O(V)
package main

import (
	"container/heap"
	"fmt"
	"reflect"
)

// Edge is one directed, weighted adjacency-list entry.
type Edge struct {
	To     string
	Weight int
}

type heapItem struct {
	node string
	dist int
}

// minHeap implements heap.Interface ordered by distance.
type minHeap []heapItem

func (h minHeap) Len() int           { return len(h) }
func (h minHeap) Less(i, j int) bool { return h[i].dist < h[j].dist }
func (h minHeap) Swap(i, j int)      { h[i], h[j] = h[j], h[i] }

func (h *minHeap) Push(x any) { *h = append(*h, x.(heapItem)) }

func (h *minHeap) Pop() any {
	old := *h
	item := old[len(old)-1]
	*h = old[:len(old)-1]
	return item
}

// dijkstra returns the shortest distance from source to each reachable node.
// Edge weights must be non-negative. Unreachable nodes are absent from the
// result.
func dijkstra(graph map[string][]Edge, source string) map[string]int {
	distances := map[string]int{source: 0}
	pending := &minHeap{{node: source, dist: 0}}
	heap.Init(pending)
	for pending.Len() > 0 {
		current := heap.Pop(pending).(heapItem)
		if best, seen := distances[current.node]; seen && current.dist > best {
			continue // stale entry: a shorter path was already found
		}
		for _, edge := range graph[current.node] {
			candidate := current.dist + edge.Weight
			if best, seen := distances[edge.To]; !seen || candidate < best {
				distances[edge.To] = candidate
				heap.Push(pending, heapItem{node: edge.To, dist: candidate})
			}
		}
	}
	return distances
}

func main() {
	graph := map[string][]Edge{
		"a": {{"b", 1}, {"c", 4}},
		"b": {{"c", 2}, {"d", 6}},
		"c": {{"d", 1}},
		"d": {},
		"e": {{"a", 10}}, // "e" is unreachable from "a"
	}

	distances := dijkstra(graph, "a")
	expected := map[string]int{"a": 0, "b": 1, "c": 3, "d": 4}
	if !reflect.DeepEqual(distances, expected) {
		panic(fmt.Sprintf("unexpected distances: %v", distances))
	}

	if got := dijkstra(graph, "d"); !reflect.DeepEqual(got, map[string]int{"d": 0}) {
		panic(fmt.Sprintf("sink node should reach only itself: %v", got))
	}

	if got := dijkstra(graph, "e")["d"]; got != 14 {
		panic(fmt.Sprintf("unexpected distance from e to d: %d", got))
	}

	fmt.Println("dijkstra: all tests passed")
}
