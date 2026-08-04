/**
 * Sieve of Eratosthenes.
 *
 * Returns all prime numbers up to and including n by iteratively marking the
 * multiples of each prime as composite.
 *
 * Complexity: O(n log log n) time, O(n) space.
 */

function sieveOfEratosthenes(n: number): number[] {
  if (n < 2) {
    return [];
  }

  const isPrime: boolean[] = new Array(n + 1).fill(true);
  isPrime[0] = false;
  isPrime[1] = false;

  for (let p = 2; p * p <= n; p++) {
    if (isPrime[p]) {
      for (let multiple = p * p; multiple <= n; multiple += p) {
        isPrime[multiple] = false;
      }
    }
  }

  const primes: number[] = [];
  for (let i = 2; i <= n; i++) {
    if (isPrime[i]) {
      primes.push(i);
    }
  }
  return primes;
}

function main(): void {
  const assert = (condition: boolean, message: string): void => {
    if (!condition) {
      throw new Error(`Assertion failed: ${message}`);
    }
  };

  const arraysEqual = (a: number[], b: number[]): boolean =>
    a.length === b.length && a.every((value, i) => value === b[i]);

  assert(arraysEqual(sieveOfEratosthenes(1), []), "no primes below 2");
  assert(arraysEqual(sieveOfEratosthenes(2), [2]), "primes up to 2");
  assert(
    arraysEqual(sieveOfEratosthenes(30), [2, 3, 5, 7, 11, 13, 17, 19, 23, 29]),
    "primes up to 30"
  );
  assert(sieveOfEratosthenes(1000).length === 168, "168 primes below 1000");
  console.log("sieve-of-eratosthenes: all tests passed");
}

main();
