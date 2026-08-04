// Binary search: find a target value in a sorted slice.
//
// Repeatedly halve the search interval [low, high] until the target is found
// or the interval is empty.
//
// Convention: returns the index of the target if present, otherwise -1.
// If the target occurs multiple times, any one of its indices may be
// returned. The input slice must be sorted in ascending order.
//
// Time complexity:  O(log n) worst/average, O(1) best.
// Space complexity: O(1) (iterative).
package main

import "fmt"

// BinarySearch returns an index of target in the sorted slice items,
// or -1 if it is absent.
func BinarySearch(items []int, target int) int {
	low := 0
	high := len(items) - 1
	for low <= high {
		middle := low + (high-low)/2
		switch {
		case items[middle] == target:
			return middle
		case items[middle] < target:
			low = middle + 1
		default:
			high = middle - 1
		}
	}
	return -1
}

func main() {
	data := []int{-3, 0, 1, 2, 5, 6, 9}

	check := func(got, want int, label string) {
		if got != want {
			panic(fmt.Sprintf("binary-search failed (%s): got %d, want %d", label, got, want))
		}
	}

	check(BinarySearch(data, -3), 0, "first element")
	check(BinarySearch(data, 9), 6, "last element")
	check(BinarySearch(data, 2), 3, "middle element")
	check(BinarySearch(data, 4), -1, "absent, inside range")
	check(BinarySearch(data, -10), -1, "absent, below range")
	check(BinarySearch(data, 100), -1, "absent, above range")
	check(BinarySearch([]int{}, 1), -1, "empty slice")
	check(BinarySearch([]int{7}, 7), 0, "single element, present")
	check(BinarySearch([]int{7}, 8), -1, "single element, absent")

	fmt.Println("binary-search: all tests passed")
}
