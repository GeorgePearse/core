"""Quicksort: in-place divide-and-conquer sorting via Lomuto partitioning.

Time complexity:  O(n log n) best/average, O(n^2) worst (already-sorted input
                  with a bad pivot choice; mitigated here by last-element pivot
                  on the canonical formulation).
Space complexity: O(log n) average for the recursion stack.

Not stable. Sorts the list in place.
"""

from __future__ import annotations


def quicksort(items: list[int], low: int = 0, high: int | None = None) -> None:
    """Sort items[low..high] in place using quicksort."""
    if high is None:
        high = len(items) - 1
    if low < high:
        pivot_index = partition(items, low, high)
        quicksort(items, low, pivot_index - 1)
        quicksort(items, pivot_index + 1, high)


def partition(items: list[int], low: int, high: int) -> int:
    """Lomuto partition: place items[high] (the pivot) into its final
    position and return that position. Elements <= pivot end up to its left,
    elements > pivot to its right."""
    pivot = items[high]
    boundary = low  # first index of the "greater than pivot" region
    for i in range(low, high):
        if items[i] <= pivot:
            items[boundary], items[i] = items[i], items[boundary]
            boundary += 1
    items[boundary], items[high] = items[high], items[boundary]
    return boundary


if __name__ == "__main__":
    data = [5, 2, 9, 1, 5, 6, -3, 0]
    quicksort(data)
    assert data == [-3, 0, 1, 2, 5, 5, 6, 9], data

    empty: list[int] = []
    quicksort(empty)
    assert empty == []

    single = [42]
    quicksort(single)
    assert single == [42]

    already_sorted = [1, 2, 3, 4]
    quicksort(already_sorted)
    assert already_sorted == [1, 2, 3, 4]

    print("quicksort: all tests passed")
