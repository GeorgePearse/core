/**
 * 0/1 Knapsack.
 *
 * Given items with weights and values and a knapsack capacity, selects a
 * subset of items (each used at most once) that maximizes total value
 * without exceeding the capacity. Bottom-up DP table; returns the maximum
 * achievable value.
 *
 * Time complexity:  O(n * W) where n is the item count and W the capacity
 * Space complexity: O(n * W)
 */

/**
 * Return the maximum total value achievable within `capacity`.
 * dp[i][w] holds the best value using the first i items with capacity w.
 */
function knapsack01(weights: number[], values: number[], capacity: number): number {
  if (weights.length !== values.length) {
    throw new Error("weights and values must have the same length");
  }

  const itemCount = weights.length;
  const dp: number[][] = Array.from({ length: itemCount + 1 }, () =>
    new Array<number>(capacity + 1).fill(0),
  );

  for (let i = 1; i <= itemCount; i++) {
    const weight = weights[i - 1];
    const value = values[i - 1];
    for (let w = 0; w <= capacity; w++) {
      // Option 1: skip item i.
      dp[i][w] = dp[i - 1][w];
      // Option 2: take item i, if it fits.
      if (weight <= w) {
        dp[i][w] = Math.max(dp[i][w], dp[i - 1][w - weight] + value);
      }
    }
  }

  return dp[itemCount][capacity];
}

function main(): void {
  console.assert(knapsack01([1, 3, 4, 5], [1, 4, 5, 7], 7) === 9);
  console.assert(knapsack01([10, 20, 30], [60, 100, 120], 50) === 220);
  console.assert(knapsack01([], [], 10) === 0);
  console.assert(knapsack01([5], [100], 4) === 0);
  console.assert(knapsack01([2, 2, 2], [10, 10, 10], 6) === 30);
  console.log("knapsack-01: all tests passed");
}

main();
