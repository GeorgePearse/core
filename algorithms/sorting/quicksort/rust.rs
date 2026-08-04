//! Quicksort: in-place divide-and-conquer sorting via Lomuto partitioning.
//!
//! Time complexity:  O(n log n) best/average, O(n^2) worst.
//! Space complexity: O(log n) average for the recursion stack.
//!
//! Not stable. Sorts the slice in place.

/// Sort the slice in place using quicksort.
pub fn quicksort<T: Ord>(items: &mut [T]) {
    if items.len() <= 1 {
        return;
    }
    let pivot_index = partition(items);
    let (left, right) = items.split_at_mut(pivot_index);
    quicksort(left);
    quicksort(&mut right[1..]); // skip the pivot, already in place
}

/// Lomuto partition: place the last element (the pivot) into its final
/// position and return that position.
fn partition<T: Ord>(items: &mut [T]) -> usize {
    let pivot_index = items.len() - 1;
    let mut boundary = 0; // first index of the "greater than pivot" region
    for i in 0..pivot_index {
        if items[i] <= items[pivot_index] {
            items.swap(boundary, i);
            boundary += 1;
        }
    }
    items.swap(boundary, pivot_index);
    boundary
}

fn main() {
    let mut data = vec![5, 2, 9, 1, 5, 6, -3, 0];
    quicksort(&mut data);
    assert_eq!(data, vec![-3, 0, 1, 2, 5, 5, 6, 9]);

    let mut empty: Vec<i32> = vec![];
    quicksort(&mut empty);
    assert!(empty.is_empty());

    let mut single = vec![42];
    quicksort(&mut single);
    assert_eq!(single, vec![42]);

    println!("quicksort: all tests passed");
}

#[cfg(test)]
mod tests {
    use super::quicksort;

    #[test]
    fn sorts_various_inputs() {
        let mut data = vec![3, 1, 2];
        quicksort(&mut data);
        assert_eq!(data, vec![1, 2, 3]);

        let mut sorted = vec![1, 2, 3, 4];
        quicksort(&mut sorted);
        assert_eq!(sorted, vec![1, 2, 3, 4]);

        let mut reversed = vec![4, 3, 2, 1];
        quicksort(&mut reversed);
        assert_eq!(reversed, vec![1, 2, 3, 4]);
    }
}
