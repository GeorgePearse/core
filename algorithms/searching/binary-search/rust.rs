//! Binary search: find a target value in a sorted slice.
//!
//! Repeatedly halve the search interval [low, high) until the target is found
//! or the interval is empty.
//!
//! Convention: returns the index of the target as `i64` if present,
//! otherwise -1. If the target occurs multiple times, any one of its indices
//! may be returned. The input slice must be sorted in ascending order.
//!
//! Time complexity:  O(log n) worst/average, O(1) best.
//! Space complexity: O(1) (iterative).

/// Return an index of `target` in the sorted slice `items`, or -1 if absent.
pub fn binary_search<T: Ord>(items: &[T], target: &T) -> i64 {
    let mut low = 0usize;
    let mut high = items.len(); // half-open interval [low, high)
    while low < high {
        let middle = low + (high - low) / 2;
        match items[middle].cmp(target) {
            std::cmp::Ordering::Equal => return middle as i64,
            std::cmp::Ordering::Less => low = middle + 1,
            std::cmp::Ordering::Greater => high = middle,
        }
    }
    -1
}

fn main() {
    let data = [-3, 0, 1, 2, 5, 6, 9];

    assert_eq!(binary_search(&data, &-3), 0); // first element
    assert_eq!(binary_search(&data, &9), 6); // last element
    assert_eq!(binary_search(&data, &2), 3); // middle element
    assert_eq!(binary_search(&data, &4), -1); // absent, inside range
    assert_eq!(binary_search(&data, &-10), -1); // absent, below range
    assert_eq!(binary_search(&data, &100), -1); // absent, above range
    assert_eq!(binary_search::<i32>(&[], &1), -1); // empty slice
    assert_eq!(binary_search(&[7], &7), 0); // single element, present
    assert_eq!(binary_search(&[7], &8), -1); // single element, absent

    println!("binary-search: all tests passed");
}

#[cfg(test)]
mod tests {
    use super::binary_search;

    #[test]
    fn finds_present_and_absent_targets() {
        let data = [1, 3, 5, 7];
        assert_eq!(binary_search(&data, &1), 0);
        assert_eq!(binary_search(&data, &7), 3);
        assert_eq!(binary_search(&data, &4), -1);
        assert_eq!(binary_search::<i32>(&[], &4), -1);
    }
}
