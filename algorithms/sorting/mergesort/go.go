// Mergesort: stable divide-and-conquer sorting.
//
// Time complexity:  O(n log n) in all cases.
// Space complexity: O(n) auxiliary for the merge step.
//
// Stable. Returns a new sorted slice; the input is not modified.
package main

import "fmt"

// Mergesort returns a new slice containing the elements of items in sorted order.
func Mergesort(items []int) []int {
	if len(items) <= 1 {
		result := make([]int, len(items))
		copy(result, items)
		return result
	}
	middle := len(items) / 2
	left := Mergesort(items[:middle])
	right := Mergesort(items[middle:])
	return merge(left, right)
}

// merge combines two sorted slices into a single sorted slice.
// Ties take from the left slice first, which is what makes the sort stable.
func merge(left, right []int) []int {
	merged := make([]int, 0, len(left)+len(right))
	i, j := 0, 0
	for i < len(left) && j < len(right) {
		if left[i] <= right[j] {
			merged = append(merged, left[i])
			i++
		} else {
			merged = append(merged, right[j])
			j++
		}
	}
	merged = append(merged, left[i:]...)
	merged = append(merged, right[j:]...)
	return merged
}

func main() {
	assertSorted := func(got, want []int, label string) {
		if len(got) != len(want) {
			panic(fmt.Sprintf("mergesort failed (%s): got %v, want %v", label, got, want))
		}
		for i := range want {
			if got[i] != want[i] {
				panic(fmt.Sprintf("mergesort failed (%s): got %v, want %v", label, got, want))
			}
		}
	}

	assertSorted(Mergesort([]int{5, 2, 9, 1, 5, 6, -3, 0}), []int{-3, 0, 1, 2, 5, 5, 6, 9}, "mixed")
	assertSorted(Mergesort([]int{}), []int{}, "empty")
	assertSorted(Mergesort([]int{42}), []int{42}, "single")
	assertSorted(Mergesort([]int{4, 3, 2, 1}), []int{1, 2, 3, 4}, "reversed")

	original := []int{3, 1, 2}
	Mergesort(original)
	assertSorted(original, []int{3, 1, 2}, "input untouched")

	fmt.Println("mergesort: all tests passed")
}
