/**
 * Mergesort: stable divide-and-conquer sorting.
 *
 * Time complexity:  O(n log n) in all cases.
 * Space complexity: O(n) auxiliary for the merge step.
 *
 * Stable. Returns a new sorted array; the input is not modified.
 */

function mergesort(items: number[]): number[] {
  if (items.length <= 1) {
    return items.slice();
  }
  const middle = Math.floor(items.length / 2);
  const left = mergesort(items.slice(0, middle));
  const right = mergesort(items.slice(middle));
  return merge(left, right);
}

/**
 * Merge two sorted arrays into a single sorted array.
 * Ties take from the left array first, which is what makes the sort stable.
 */
function merge(left: number[], right: number[]): number[] {
  const merged: number[] = [];
  let i = 0;
  let j = 0;
  while (i < left.length && j < right.length) {
    if (left[i] <= right[j]) {
      merged.push(left[i]);
      i++;
    } else {
      merged.push(right[j]);
      j++;
    }
  }
  return merged.concat(left.slice(i), right.slice(j));
}

function main(): void {
  const sameArray = (a: number[], b: number[]): boolean =>
    JSON.stringify(a) === JSON.stringify(b);

  console.assert(
    sameArray(mergesort([5, 2, 9, 1, 5, 6, -3, 0]), [-3, 0, 1, 2, 5, 5, 6, 9]),
    "mergesort failed on mixed input",
  );
  console.assert(sameArray(mergesort([]), []), "mergesort failed on empty input");
  console.assert(sameArray(mergesort([42]), [42]), "mergesort failed on single element");
  console.assert(
    sameArray(mergesort([4, 3, 2, 1]), [1, 2, 3, 4]),
    "mergesort failed on reversed input",
  );

  const original = [3, 1, 2];
  mergesort(original);
  console.assert(sameArray(original, [3, 1, 2]), "mergesort mutated its input");

  console.log("mergesort: all tests passed");
}

main();
