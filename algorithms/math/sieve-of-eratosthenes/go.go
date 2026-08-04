// Sieve of Eratosthenes.
//
// Returns all prime numbers up to and including n by iteratively marking the
// multiples of each prime as composite.
//
// Complexity: O(n log log n) time, O(n) space.
package main

import "fmt"

// SieveOfEratosthenes returns a sorted slice of all primes p with 2 <= p <= n.
func SieveOfEratosthenes(n int) []int {
	if n < 2 {
		return nil
	}

	isPrime := make([]bool, n+1)
	for i := 2; i <= n; i++ {
		isPrime[i] = true
	}

	for p := 2; p*p <= n; p++ {
		if isPrime[p] {
			for multiple := p * p; multiple <= n; multiple += p {
				isPrime[multiple] = false
			}
		}
	}

	primes := make([]int, 0)
	for i := 2; i <= n; i++ {
		if isPrime[i] {
			primes = append(primes, i)
		}
	}
	return primes
}

func main() {
	equal := func(a, b []int) bool {
		if len(a) != len(b) {
			return false
		}
		for i := range a {
			if a[i] != b[i] {
				return false
			}
		}
		return true
	}

	if len(SieveOfEratosthenes(1)) != 0 {
		panic("expected no primes below 2")
	}
	if !equal(SieveOfEratosthenes(2), []int{2}) {
		panic("expected [2] for n=2")
	}
	if !equal(SieveOfEratosthenes(30), []int{2, 3, 5, 7, 11, 13, 17, 19, 23, 29}) {
		panic("wrong primes up to 30")
	}
	if len(SieveOfEratosthenes(1000)) != 168 {
		panic("expected 168 primes below 1000")
	}
	fmt.Println("sieve-of-eratosthenes: all tests passed")
}
