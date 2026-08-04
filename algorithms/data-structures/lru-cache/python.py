"""LRU (least recently used) cache.

Fixed-capacity key-value cache that evicts the least recently used entry when
full. Uses collections.OrderedDict, which maintains insertion order and moves
entries to the end in O(1), giving O(1) get and put.

Complexity: O(1) per get/put, O(capacity) space.
"""

from __future__ import annotations

from collections import OrderedDict


class LRUCache:
    """Least-recently-used cache with O(1) get and put."""

    def __init__(self, capacity: int) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        self.capacity = capacity
        self._entries: OrderedDict[int, int] = OrderedDict()

    def get(self, key: int) -> int:
        """Return the value for key, marking it most recently used. -1 if absent."""
        if key not in self._entries:
            return -1
        self._entries.move_to_end(key)
        return self._entries[key]

    def put(self, key: int, value: int) -> None:
        """Insert or update key, evicting the least recently used entry if full."""
        if key in self._entries:
            self._entries.move_to_end(key)
        self._entries[key] = value
        if len(self._entries) > self.capacity:
            self._entries.popitem(last=False)  # evict least recently used

    def __len__(self) -> int:
        return len(self._entries)


if __name__ == "__main__":
    cache = LRUCache(2)
    cache.put(1, 1)
    cache.put(2, 2)
    assert cache.get(1) == 1  # 1 becomes most recently used
    cache.put(3, 3)  # evicts key 2
    assert cache.get(2) == -1
    assert cache.get(3) == 3
    cache.put(1, 10)  # update existing key
    assert cache.get(1) == 10
    cache.put(4, 4)  # evicts key 3 (1 was refreshed by the update)
    assert cache.get(3) == -1
    assert cache.get(1) == 10
    assert cache.get(4) == 4
    assert len(cache) == 2
    print("lru-cache: all tests passed")
