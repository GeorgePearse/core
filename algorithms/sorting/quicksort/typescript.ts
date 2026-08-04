/**
 * Quicksort: in-place divide-and-conquer sorting via Lomuto partitioning.
 *
 * Time complexity:  O(n log n) best/average, O(n^2) worst.
 * Space complexity: O(log n) average for the recursion stack.
 *
 * Not stable. Sorts the array in place.
 */

function quicksort(items: number[], low = 0, high = items.length - 1): void {
  if (low < high) {
    const pivotIndex = partition(items, low, high);
    quicksort(items, low, pivotIndex - 1);
    quicksort(items, pivotIndex + 1, high);
  }
}

/**
 * Lomuto partition: place items[high] (the pivot) into its final position
 * and return that position.
 */
function partition(items: number[], low: number, high: number): number {
  const pivot = items[high];
  let boundary = low; // first index of the "greater than pivot" region
  for (let i = low; i < high; i++) {
    if (items[i] <= pivot) {
      [items[boundary], items[i]] = [items[i], items[boundary]];
      boundary++;
    }
  }
  [items[boundary], items[high]] = [items[high], items[boundary]];
  return boundary;
}

function main(): void {
  const data = [5, 2, 9, 1, 5, 6, -3, 0];
  quicksort(data);
  console.assert(
    JSON.stringify(data) === JSON.stringify([-3, 0, 1, 2, 5, 5, 6, 9]),
    "quicksort failed on mixed input",
  );

  const empty: number[] = [];
  quicksort(empty);
  console.assert(empty.length === 0, "quicksort failed on empty input");

  const single = [42];
  quicksort(single);
  console.assert(single[0] === 42, "quicksort failed on single element");

  console.log("quicksort: all tests passed");
}

main();
