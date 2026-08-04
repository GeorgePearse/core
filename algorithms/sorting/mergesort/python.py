"""Mergesort: stable divide-and-conquer sorting.

Time complexity:  O(n log n) in all cases.
Space complexity: O(n) auxiliary for the merge step.

Stable. Returns a new sorted list; the input is not modified.
"""

from __future__ import annotations


def mergesort(items: list[int]) -> list[int]:
    """Return a new list containing the elements of items in sorted order."""
    if len(items) <= 1:
        return list(items)
    middle = len(items) // 2
    left = mergesort(items[:middle])
    right = mergesort(items[middle:])
    return merge(left, right)


def merge(left: list[int], right: list[int]) -> list[int]:
    """Merge two sorted lists into a single sorted list.

    Ties take from the left list first, which is what makes the sort stable.
    """
    merged: list[int] = []
    i = j = 0
    while i < len(left) and j < len(right):
        if left[i] <= right[j]:
            merged.append(left[i])
            i += 1
        else:
            merged.append(right[j])
            j += 1
    merged.extend(left[i:])
    merged.extend(right[j:])
    return merged


if __name__ == "__main__":
    assert mergesort([5, 2, 9, 1, 5, 6, -3, 0]) == [-3, 0, 1, 2, 5, 5, 6, 9]
    assert mergesort([]) == []
    assert mergesort([42]) == [42]
    assert mergesort([1, 2, 3, 4]) == [1, 2, 3, 4]
    assert mergesort([4, 3, 2, 1]) == [1, 2, 3, 4]

    original = [3, 1, 2]
    assert mergesort(original) == [1, 2, 3]
    assert original == [3, 1, 2]  # input untouched

    print("mergesort: all tests passed")
