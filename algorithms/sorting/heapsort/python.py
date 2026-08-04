"""Heapsort: in-place sorting via a binary max-heap.

Build a max-heap over the array, then repeatedly swap the root (maximum)
to the end of the unsorted region and sift the new root down.

Time complexity:  O(n log n) in all cases.
Space complexity: O(1) auxiliary (iterative sift-down, in-place).

Not stable. Sorts the list in place.
"""

from __future__ import annotations


def heapsort(items: list[int]) -> None:
    """Sort the list in place using heapsort."""
    n = len(items)

    # Build a max-heap: sift down every internal node, deepest first.
    for root in range(n // 2 - 1, -1, -1):
        sift_down(items, root, n)

    # Repeatedly move the max to the end and shrink the heap.
    for end in range(n - 1, 0, -1):
        items[0], items[end] = items[end], items[0]
        sift_down(items, 0, end)


def sift_down(items: list[int], root: int, heap_size: int) -> None:
    """Restore the max-heap property for the subtree rooted at root,
    considering only items[:heap_size]."""
    while True:
        largest = root
        left = 2 * root + 1
        right = 2 * root + 2
        if left < heap_size and items[left] > items[largest]:
            largest = left
        if right < heap_size and items[right] > items[largest]:
            largest = right
        if largest == root:
            return
        items[root], items[largest] = items[largest], items[root]
        root = largest


if __name__ == "__main__":
    data = [5, 2, 9, 1, 5, 6, -3, 0]
    heapsort(data)
    assert data == [-3, 0, 1, 2, 5, 5, 6, 9], data

    empty: list[int] = []
    heapsort(empty)
    assert empty == []

    single = [42]
    heapsort(single)
    assert single == [42]

    reversed_input = [4, 3, 2, 1]
    heapsort(reversed_input)
    assert reversed_input == [1, 2, 3, 4]

    print("heapsort: all tests passed")
