// 0/1 Knapsack.
//
// Given items with weights and values and a knapsack capacity, selects a
// subset of items (each used at most once) that maximizes total value
// without exceeding the capacity. Bottom-up DP table; returns the maximum
// achievable value.
//
// Time complexity:  O(n * W) where n is the item count and W the capacity
// Space complexity: O(n * W)
package main

import "fmt"

// knapsack01 returns the maximum total value achievable within capacity.
// dp[i][w] holds the best value using the first i items with capacity w.
func knapsack01(weights, values []int, capacity int) int {
	if len(weights) != len(values) {
		panic("weights and values must have the same length")
	}

	itemCount := len(weights)
	dp := make([][]int, itemCount+1)
	for i := range dp {
		dp[i] = make([]int, capacity+1)
	}

	for i := 1; i <= itemCount; i++ {
		weight, value := weights[i-1], values[i-1]
		for w := 0; w <= capacity; w++ {
			// Option 1: skip item i.
			dp[i][w] = dp[i-1][w]
			// Option 2: take item i, if it fits.
			if weight <= w {
				if taken := dp[i-1][w-weight] + value; taken > dp[i][w] {
					dp[i][w] = taken
				}
			}
		}
	}

	return dp[itemCount][capacity]
}

func main() {
	if got := knapsack01([]int{1, 3, 4, 5}, []int{1, 4, 5, 7}, 7); got != 9 {
		panic(fmt.Sprintf("expected 9, got %d", got))
	}
	if got := knapsack01([]int{10, 20, 30}, []int{60, 100, 120}, 50); got != 220 {
		panic(fmt.Sprintf("expected 220, got %d", got))
	}
	if got := knapsack01(nil, nil, 10); got != 0 {
		panic(fmt.Sprintf("expected 0, got %d", got))
	}
	if got := knapsack01([]int{5}, []int{100}, 4); got != 0 {
		panic(fmt.Sprintf("expected 0, got %d", got))
	}
	if got := knapsack01([]int{2, 2, 2}, []int{10, 10, 10}, 6); got != 30 {
		panic(fmt.Sprintf("expected 30, got %d", got))
	}
	fmt.Println("knapsack-01: all tests passed")
}
