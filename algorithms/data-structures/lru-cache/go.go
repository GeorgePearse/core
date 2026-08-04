// LRU (least recently used) cache.
//
// Fixed-capacity key-value cache that evicts the least recently used entry
// when full. Uses a map from key to list element plus the standard library's
// container/list doubly linked list, ordered from most recently used (front)
// to least recently used (back).
//
// Complexity: O(1) per Get/Put, O(capacity) space.
package main

import (
	"container/list"
	"fmt"
)

type entry struct {
	key   int
	value int
}

// LRUCache is a least-recently-used cache with O(1) Get and Put.
type LRUCache struct {
	capacity int
	elements map[int]*list.Element
	order    *list.List // front = most recently used, back = least recently used
}

// NewLRUCache creates an empty cache holding at most capacity entries.
func NewLRUCache(capacity int) *LRUCache {
	if capacity <= 0 {
		panic("capacity must be positive")
	}
	return &LRUCache{
		capacity: capacity,
		elements: make(map[int]*list.Element, capacity),
		order:    list.New(),
	}
}

// Get returns the value for key, marking it most recently used.
// The second return value reports whether the key was present.
func (c *LRUCache) Get(key int) (int, bool) {
	element, ok := c.elements[key]
	if !ok {
		return 0, false
	}
	c.order.MoveToFront(element)
	return element.Value.(*entry).value, true
}

// Put inserts or updates key, evicting the least recently used entry if full.
func (c *LRUCache) Put(key, value int) {
	if element, ok := c.elements[key]; ok {
		element.Value.(*entry).value = value
		c.order.MoveToFront(element)
		return
	}

	if len(c.elements) == c.capacity {
		lru := c.order.Back()
		c.order.Remove(lru)
		delete(c.elements, lru.Value.(*entry).key)
	}

	c.elements[key] = c.order.PushFront(&entry{key: key, value: value})
}

// Len returns the number of entries currently in the cache.
func (c *LRUCache) Len() int {
	return len(c.elements)
}

func main() {
	cache := NewLRUCache(2)
	cache.Put(1, 1)
	cache.Put(2, 2)

	if v, ok := cache.Get(1); !ok || v != 1 { // 1 becomes most recently used
		panic("expected Get(1) == 1")
	}
	cache.Put(3, 3) // evicts key 2
	if _, ok := cache.Get(2); ok {
		panic("expected key 2 evicted")
	}
	if v, ok := cache.Get(3); !ok || v != 3 {
		panic("expected Get(3) == 3")
	}
	cache.Put(1, 10) // update existing key
	if v, ok := cache.Get(1); !ok || v != 10 {
		panic("expected Get(1) == 10 after update")
	}
	cache.Put(4, 4) // evicts key 3 (1 was refreshed by the update)
	if _, ok := cache.Get(3); ok {
		panic("expected key 3 evicted")
	}
	if v, ok := cache.Get(1); !ok || v != 10 {
		panic("expected key 1 retained")
	}
	if v, ok := cache.Get(4); !ok || v != 4 {
		panic("expected Get(4) == 4")
	}
	if cache.Len() != 2 {
		panic("expected size capped at capacity")
	}

	fmt.Println("lru-cache: all tests passed")
}
