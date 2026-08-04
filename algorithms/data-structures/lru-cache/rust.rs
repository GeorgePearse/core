//! LRU (least recently used) cache.
//!
//! Fixed-capacity key-value cache that evicts the least recently used entry
//! when full. Uses a `HashMap` from key to node index plus a doubly linked
//! list stored in an arena (`Vec` of nodes with prev/next indices), the
//! idiomatic safe-Rust formulation. The list is ordered from most recently
//! used (head) to least recently used (tail).
//!
//! Complexity: O(1) per get/put, O(capacity) space.

use std::collections::HashMap;

struct Node {
    key: i32,
    value: i32,
    prev: Option<usize>,
    next: Option<usize>,
}

pub struct LruCache {
    capacity: usize,
    map: HashMap<i32, usize>,
    nodes: Vec<Node>,
    head: Option<usize>, // most recently used
    tail: Option<usize>, // least recently used
}

impl LruCache {
    pub fn new(capacity: usize) -> Self {
        assert!(capacity > 0, "capacity must be positive");
        LruCache {
            capacity,
            map: HashMap::with_capacity(capacity),
            nodes: Vec::with_capacity(capacity),
            head: None,
            tail: None,
        }
    }

    /// Return the value for `key`, marking it most recently used.
    pub fn get(&mut self, key: i32) -> Option<i32> {
        let &index = self.map.get(&key)?;
        self.detach(index);
        self.push_front(index);
        Some(self.nodes[index].value)
    }

    /// Insert or update `key`, evicting the least recently used entry if full.
    pub fn put(&mut self, key: i32, value: i32) {
        if let Some(&index) = self.map.get(&key) {
            self.nodes[index].value = value;
            self.detach(index);
            self.push_front(index);
            return;
        }

        let index = if self.map.len() == self.capacity {
            // Evict the least recently used entry and reuse its slot.
            let lru = self.tail.expect("non-empty cache has a tail");
            self.detach(lru);
            self.map.remove(&self.nodes[lru].key);
            self.nodes[lru].key = key;
            self.nodes[lru].value = value;
            lru
        } else {
            self.nodes.push(Node {
                key,
                value,
                prev: None,
                next: None,
            });
            self.nodes.len() - 1
        };

        self.map.insert(key, index);
        self.push_front(index);
    }

    pub fn len(&self) -> usize {
        self.map.len()
    }

    pub fn is_empty(&self) -> bool {
        self.map.is_empty()
    }

    /// Unlink the node at `index` from the recency list.
    fn detach(&mut self, index: usize) {
        let (prev, next) = (self.nodes[index].prev, self.nodes[index].next);
        match prev {
            Some(p) => self.nodes[p].next = next,
            None => self.head = next,
        }
        match next {
            Some(n) => self.nodes[n].prev = prev,
            None => self.tail = prev,
        }
        self.nodes[index].prev = None;
        self.nodes[index].next = None;
    }

    /// Insert the node at `index` at the head (most recently used).
    fn push_front(&mut self, index: usize) {
        self.nodes[index].prev = None;
        self.nodes[index].next = self.head;
        if let Some(old_head) = self.head {
            self.nodes[old_head].prev = Some(index);
        }
        self.head = Some(index);
        if self.tail.is_none() {
            self.tail = Some(index);
        }
    }
}

fn main() {
    let mut cache = LruCache::new(2);
    cache.put(1, 1);
    cache.put(2, 2);
    assert_eq!(cache.get(1), Some(1)); // 1 becomes most recently used
    cache.put(3, 3); // evicts key 2
    assert_eq!(cache.get(2), None);
    assert_eq!(cache.get(3), Some(3));
    cache.put(1, 10); // update existing key
    assert_eq!(cache.get(1), Some(10));
    cache.put(4, 4); // evicts key 3 (1 was refreshed by the update)
    assert_eq!(cache.get(3), None);
    assert_eq!(cache.get(1), Some(10));
    assert_eq!(cache.get(4), Some(4));
    assert_eq!(cache.len(), 2);
    println!("lru-cache: all tests passed");
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn evicts_least_recently_used() {
        let mut cache = LruCache::new(2);
        cache.put(1, 1);
        cache.put(2, 2);
        assert_eq!(cache.get(1), Some(1));
        cache.put(3, 3); // evicts 2, the least recently used
        assert_eq!(cache.get(2), None);
        assert_eq!(cache.get(1), Some(1));
        assert_eq!(cache.get(3), Some(3));
    }

    #[test]
    fn update_refreshes_recency() {
        let mut cache = LruCache::new(2);
        cache.put(1, 1);
        cache.put(2, 2);
        cache.put(1, 10); // refreshes key 1
        cache.put(3, 3); // evicts 2
        assert_eq!(cache.get(1), Some(10));
        assert_eq!(cache.get(2), None);
    }

    #[test]
    fn capacity_one() {
        let mut cache = LruCache::new(1);
        cache.put(1, 1);
        cache.put(2, 2);
        assert_eq!(cache.get(1), None);
        assert_eq!(cache.get(2), Some(2));
        assert_eq!(cache.len(), 1);
    }
}
