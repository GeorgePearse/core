// Quicksort: in-place divide-and-conquer sorting via Lomuto partitioning.
//
// Time complexity:  O(n log n) best/average, O(n^2) worst.
// Space complexity: O(log n) average for the recursion stack.
//
// Not stable. Sorts the slice in place.
package main

import "fmt"

// Quicksort sorts items[low..high] in place.
func Quicksort(items []int, low, high int) {
	if low < high {
		pivotIndex := partition(items, low, high)
		Quicksort(items, low, pivotIndex-1)
		Quicksort(items, pivotIndex+1, high)
	}
}

// partition applies the Lomuto scheme: it places items[high] (the pivot)
// into its final position and returns that position.
func partition(items []int, low, high int) int {
	pivot := items[high]
	boundary := low // first index of the "greater than pivot" region
	for i := low; i < high; i++ {
		if items[i] <= pivot {
			items[boundary], items[i] = items[i], items[boundary]
			boundary++
		}
	}
	items[boundary], items[high] = items[high], items[boundary]
	return boundary
}

func main() {
	data := []int{5, 2, 9, 1, 5, 6, -3, 0}
	Quicksort(data, 0, len(data)-1)
	want := []int{-3, 0, 1, 2, 5, 5, 6, 9}
	for i := range want {
		if data[i] != want[i] {
			panic(fmt.Sprintf("quicksort failed: got %v, want %v", data, want))
		}
	}

	empty := []int{}
	Quicksort(empty, 0, len(empty)-1)
	if len(empty) != 0 {
		panic("quicksort failed on empty input")
	}

	single := []int{42}
	Quicksort(single, 0, len(single)-1)
	if single[0] != 42 {
		panic("quicksort failed on single element")
	}

	fmt.Println("quicksort: all tests passed")
}
