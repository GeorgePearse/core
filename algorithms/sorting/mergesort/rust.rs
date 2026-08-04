//! Mergesort: stable divide-and-conquer sorting.
//!
//! Time complexity:  O(n log n) in all cases.
//! Space complexity: O(n) auxiliary for the merge step.
//!
//! Stable. Returns a new sorted vector; the input slice is not modified.

/// Return a new vector containing the elements of `items` in sorted order.
pub fn mergesort<T: Ord + Clone>(items: &[T]) -> Vec<T> {
    if items.len() <= 1 {
        return items.to_vec();
    }
    let middle = items.len() / 2;
    let left = mergesort(&items[..middle]);
    let right = mergesort(&items[middle..]);
    merge(left, right)
}

/// Merge two sorted vectors into a single sorted vector.
///
/// Ties take from the left vector first, which is what makes the sort stable.
fn merge<T: Ord>(left: Vec<T>, right: Vec<T>) -> Vec<T> {
    let mut merged = Vec::with_capacity(left.len() + right.len());
    let mut left_iter = left.into_iter().peekable();
    let mut right_iter = right.into_iter().peekable();

    while let (Some(l), Some(r)) = (left_iter.peek(), right_iter.peek()) {
        if l <= r {
            merged.push(left_iter.next().unwrap());
        } else {
            merged.push(right_iter.next().unwrap());
        }
    }
    merged.extend(left_iter);
    merged.extend(right_iter);
    merged
}

fn main() {
    assert_eq!(
        mergesort(&[5, 2, 9, 1, 5, 6, -3, 0]),
        vec![-3, 0, 1, 2, 5, 5, 6, 9]
    );
    assert_eq!(mergesort::<i32>(&[]), Vec::<i32>::new());
    assert_eq!(mergesort(&[42]), vec![42]);
    assert_eq!(mergesort(&[4, 3, 2, 1]), vec![1, 2, 3, 4]);

    println!("mergesort: all tests passed");
}

#[cfg(test)]
mod tests {
    use super::mergesort;

    #[test]
    fn sorts_various_inputs() {
        assert_eq!(mergesort(&[3, 1, 2]), vec![1, 2, 3]);
        assert_eq!(mergesort(&[1, 2, 3, 4]), vec![1, 2, 3, 4]);
        assert_eq!(mergesort(&[2, 2, 1, 1]), vec![1, 1, 2, 2]);
    }
}
