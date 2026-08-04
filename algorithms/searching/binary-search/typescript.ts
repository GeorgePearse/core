/**
 * Binary search: find a target value in a sorted array.
 *
 * Repeatedly halve the search interval [low, high] until the target is found
 * or the interval is empty.
 *
 * Convention: returns the index of the target if present, otherwise -1.
 * If the target occurs multiple times, any one of its indices may be
 * returned. The input array must be sorted in ascending order.
 *
 * Time complexity:  O(log n) worst/average, O(1) best.
 * Space complexity: O(1) (iterative).
 */

function binarySearch(items: number[], target: number): number {
  let low = 0;
  let high = items.length - 1;
  while (low <= high) {
    const middle = Math.floor((low + high) / 2);
    if (items[middle] === target) {
      return middle;
    }
    if (items[middle] < target) {
      low = middle + 1;
    } else {
      high = middle - 1;
    }
  }
  return -1;
}

function main(): void {
  const data = [-3, 0, 1, 2, 5, 6, 9];

  console.assert(binarySearch(data, -3) === 0, "first element");
  console.assert(binarySearch(data, 9) === 6, "last element");
  console.assert(binarySearch(data, 2) === 3, "middle element");
  console.assert(binarySearch(data, 4) === -1, "absent, inside range");
  console.assert(binarySearch(data, -10) === -1, "absent, below range");
  console.assert(binarySearch(data, 100) === -1, "absent, above range");
  console.assert(binarySearch([], 1) === -1, "empty array");
  console.assert(binarySearch([7], 7) === 0, "single element, present");
  console.assert(binarySearch([7], 8) === -1, "single element, absent");

  console.log("binary-search: all tests passed");
}

main();
