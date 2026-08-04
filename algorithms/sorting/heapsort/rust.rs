//! Heapsort: in-place sorting via a binary max-heap.
//!
//! Build a max-heap over the slice, then repeatedly swap the root (maximum)
//! to the end of the unsorted region and sift the new root down.
//!
//! Time complexity:  O(n log n) in all cases.
//! Space complexity: O(1) auxiliary (iterative sift-down, in-place).
//!
//! Not stable. Sorts the slice in place.

/// Sort the slice in place using heapsort.
pub fn heapsort<T: Ord>(items: &mut [T]) {
    let n = items.len();
    if n <= 1 {
        return;
    }

    // Build a max-heap: sift down every internal node, deepest first.
    for root in (0..n / 2).rev() {
        sift_down(items, root, n);
    }

    // Repeatedly move the max to the end and shrink the heap.
    for end in (1..n).rev() {
        items.swap(0, end);
        sift_down(items, 0, end);
    }
}

/// Restore the max-heap property for the subtree rooted at `root`,
/// considering only `items[..heap_size]`.
fn sift_down<T: Ord>(items: &mut [T], mut root: usize, heap_size: usize) {
    loop {
        let mut largest = root;
        let left = 2 * root + 1;
        let right = 2 * root + 2;
        if left < heap_size && items[left] > items[largest] {
            largest = left;
        }
        if right < heap_size && items[right] > items[largest] {
            largest = right;
        }
        if largest == root {
            return;
        }
        items.swap(root, largest);
        root = largest;
    }
}

fn main() {
    let mut data = vec![5, 2, 9, 1, 5, 6, -3, 0];
    heapsort(&mut data);
    assert_eq!(data, vec![-3, 0, 1, 2, 5, 5, 6, 9]);

    let mut empty: Vec<i32> = vec![];
    heapsort(&mut empty);
    assert!(empty.is_empty());

    let mut single = vec![42];
    heapsort(&mut single);
    assert_eq!(single, vec![42]);

    println!("heapsort: all tests passed");
}

#[cfg(test)]
mod tests {
    use super::heapsort;

    #[test]
    fn sorts_various_inputs() {
        let mut data = vec![3, 1, 2];
        heapsort(&mut data);
        assert_eq!(data, vec![1, 2, 3]);

        let mut reversed = vec![4, 3, 2, 1];
        heapsort(&mut reversed);
        assert_eq!(reversed, vec![1, 2, 3, 4]);

        let mut duplicates = vec![2, 2, 1, 1];
        heapsort(&mut duplicates);
        assert_eq!(duplicates, vec![1, 1, 2, 2]);
    }
}
