// Heapsort: in-place sorting via a binary max-heap.
//
// Build a max-heap over the slice, then repeatedly swap the root (maximum)
// to the end of the unsorted region and sift the new root down.
//
// Time complexity:  O(n log n) in all cases.
// Space complexity: O(1) auxiliary (iterative sift-down, in-place).
//
// Not stable. Sorts the slice in place.
package main

import "fmt"

// Heapsort sorts the slice in place.
func Heapsort(items []int) {
	n := len(items)

	// Build a max-heap: sift down every internal node, deepest first.
	for root := n/2 - 1; root >= 0; root-- {
		siftDown(items, root, n)
	}

	// Repeatedly move the max to the end and shrink the heap.
	for end := n - 1; end > 0; end-- {
		items[0], items[end] = items[end], items[0]
		siftDown(items, 0, end)
	}
}

// siftDown restores the max-heap property for the subtree rooted at root,
// considering only items[:heapSize].
func siftDown(items []int, root, heapSize int) {
	for {
		largest := root
		left := 2*root + 1
		right := 2*root + 2
		if left < heapSize && items[left] > items[largest] {
			largest = left
		}
		if right < heapSize && items[right] > items[largest] {
			largest = right
		}
		if largest == root {
			return
		}
		items[root], items[largest] = items[largest], items[root]
		root = largest
	}
}

func main() {
	data := []int{5, 2, 9, 1, 5, 6, -3, 0}
	Heapsort(data)
	want := []int{-3, 0, 1, 2, 5, 5, 6, 9}
	for i := range want {
		if data[i] != want[i] {
			panic(fmt.Sprintf("heapsort failed: got %v, want %v", data, want))
		}
	}

	empty := []int{}
	Heapsort(empty)
	if len(empty) != 0 {
		panic("heapsort failed on empty input")
	}

	single := []int{42}
	Heapsort(single)
	if single[0] != 42 {
		panic("heapsort failed on single element")
	}

	fmt.Println("heapsort: all tests passed")
}
