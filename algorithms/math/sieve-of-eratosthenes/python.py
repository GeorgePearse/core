"""Sieve of Eratosthenes.

Returns all prime numbers up to and including n by iteratively marking the
multiples of each prime as composite.

Complexity: O(n log log n) time, O(n) space.
"""

from __future__ import annotations


def sieve_of_eratosthenes(n: int) -> list[int]:
    """Return a sorted list of all primes p with 2 <= p <= n."""
    if n < 2:
        return []

    is_prime = [True] * (n + 1)
    is_prime[0] = is_prime[1] = False

    p = 2
    while p * p <= n:
        if is_prime[p]:
            for multiple in range(p * p, n + 1, p):
                is_prime[multiple] = False
        p += 1

    return [i for i, prime in enumerate(is_prime) if prime]


if __name__ == "__main__":
    assert sieve_of_eratosthenes(-5) == []
    assert sieve_of_eratosthenes(1) == []
    assert sieve_of_eratosthenes(2) == [2]
    assert sieve_of_eratosthenes(30) == [2, 3, 5, 7, 11, 13, 17, 19, 23, 29]
    assert len(sieve_of_eratosthenes(1000)) == 168
    print("sieve-of-eratosthenes: all tests passed")
