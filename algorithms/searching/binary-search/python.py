"""Binary search: find a target value in a sorted list.

Repeatedly halve the search interval [low, high] until the target is found
or the interval is empty.

Convention: returns the index of the target if present, otherwise -1.
If the target occurs multiple times, any one of its indices may be returned.
The input list must be sorted in ascending order.

Time complexity:  O(log n) worst/average, O(1) best.
Space complexity: O(1) (iterative).
"""

from __future__ import annotations


def binary_search(items: list[int], target: int) -> int:
    """Return an index of target in the sorted list items, or -1 if absent."""
    low = 0
    high = len(items) - 1
    while low <= high:
        middle = (low + high) // 2
        if items[middle] == target:
            return middle
        if items[middle] < target:
            low = middle + 1
        else:
            high = middle - 1
    return -1


if __name__ == "__main__":
    data = [-3, 0, 1, 2, 5, 6, 9]

    assert binary_search(data, -3) == 0  # first element
    assert binary_search(data, 9) == 6  # last element
    assert binary_search(data, 2) == 3  # middle element
    assert binary_search(data, 4) == -1  # absent, inside range
    assert binary_search(data, -10) == -1  # absent, below range
    assert binary_search(data, 100) == -1  # absent, above range
    assert binary_search([], 1) == -1  # empty list
    assert binary_search([7], 7) == 0  # single element, present
    assert binary_search([7], 8) == -1  # single element, absent

    print("binary-search: all tests passed")
