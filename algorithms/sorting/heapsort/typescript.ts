/**
 * Heapsort: in-place sorting via a binary max-heap.
 *
 * Build a max-heap over the array, then repeatedly swap the root (maximum)
 * to the end of the unsorted region and sift the new root down.
 *
 * Time complexity:  O(n log n) in all cases.
 * Space complexity: O(1) auxiliary (iterative sift-down, in-place).
 *
 * Not stable. Sorts the array in place.
 */

function heapsort(items: number[]): void {
  const n = items.length;

  // Build a max-heap: sift down every internal node, deepest first.
  for (let root = Math.floor(n / 2) - 1; root >= 0; root--) {
    siftDown(items, root, n);
  }

  // Repeatedly move the max to the end and shrink the heap.
  for (let end = n - 1; end > 0; end--) {
    [items[0], items[end]] = [items[end], items[0]];
    siftDown(items, 0, end);
  }
}

/**
 * Restore the max-heap property for the subtree rooted at `root`,
 * considering only items[0..heapSize).
 */
function siftDown(items: number[], root: number, heapSize: number): void {
  for (;;) {
    let largest = root;
    const left = 2 * root + 1;
    const right = 2 * root + 2;
    if (left < heapSize && items[left] > items[largest]) {
      largest = left;
    }
    if (right < heapSize && items[right] > items[largest]) {
      largest = right;
    }
    if (largest === root) {
      return;
    }
    [items[root], items[largest]] = [items[largest], items[root]];
    root = largest;
  }
}

function main(): void {
  const data = [5, 2, 9, 1, 5, 6, -3, 0];
  heapsort(data);
  console.assert(
    JSON.stringify(data) === JSON.stringify([-3, 0, 1, 2, 5, 5, 6, 9]),
    "heapsort failed on mixed input",
  );

  const empty: number[] = [];
  heapsort(empty);
  console.assert(empty.length === 0, "heapsort failed on empty input");

  const single = [42];
  heapsort(single);
  console.assert(single[0] === 42, "heapsort failed on single element");

  const reversed = [4, 3, 2, 1];
  heapsort(reversed);
  console.assert(
    JSON.stringify(reversed) === JSON.stringify([1, 2, 3, 4]),
    "heapsort failed on reversed input",
  );

  console.log("heapsort: all tests passed");
}

main();
