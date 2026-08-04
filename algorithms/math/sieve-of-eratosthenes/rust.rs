//! Sieve of Eratosthenes.
//!
//! Returns all prime numbers up to and including `n` by iteratively marking
//! the multiples of each prime as composite.
//!
//! Complexity: O(n log log n) time, O(n) space.

/// Return a sorted vector of all primes `p` with `2 <= p <= n`.
pub fn sieve_of_eratosthenes(n: usize) -> Vec<usize> {
    if n < 2 {
        return Vec::new();
    }

    let mut is_prime = vec![true; n + 1];
    is_prime[0] = false;
    is_prime[1] = false;

    let mut p = 2;
    while p * p <= n {
        if is_prime[p] {
            let mut multiple = p * p;
            while multiple <= n {
                is_prime[multiple] = false;
                multiple += p;
            }
        }
        p += 1;
    }

    is_prime
        .iter()
        .enumerate()
        .filter_map(|(i, &prime)| if prime { Some(i) } else { None })
        .collect()
}

fn main() {
    assert!(sieve_of_eratosthenes(1).is_empty());
    assert_eq!(sieve_of_eratosthenes(2), vec![2]);
    assert_eq!(
        sieve_of_eratosthenes(30),
        vec![2, 3, 5, 7, 11, 13, 17, 19, 23, 29]
    );
    assert_eq!(sieve_of_eratosthenes(1000).len(), 168);
    println!("sieve-of-eratosthenes: all tests passed");
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn small_limits() {
        assert!(sieve_of_eratosthenes(0).is_empty());
        assert!(sieve_of_eratosthenes(1).is_empty());
        assert_eq!(sieve_of_eratosthenes(2), vec![2]);
    }

    #[test]
    fn primes_up_to_thirty() {
        assert_eq!(
            sieve_of_eratosthenes(30),
            vec![2, 3, 5, 7, 11, 13, 17, 19, 23, 29]
        );
    }

    #[test]
    fn prime_counting() {
        assert_eq!(sieve_of_eratosthenes(1000).len(), 168);
    }
}
