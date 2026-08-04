// Knuth-Morris-Pratt (KMP) string search.
//
// Finds all start indices where a pattern occurs in a text. Precomputes a
// failure table (length of the longest proper prefix of the pattern that
// is also a suffix) so the text pointer never moves backwards.
//
// Indices are rune positions (not byte offsets), so the algorithm is
// correct for any Unicode input.
//
// Time complexity:  O(n + m) where n = text length, m = pattern length
// Space complexity: O(m) for the failure table
package main

import "fmt"

// buildFailureTable returns the KMP failure table for pattern.
// failure[i] is the length of the longest proper prefix of pattern[:i+1]
// that is also a suffix of it.
func buildFailureTable(pattern []rune) []int {
	failure := make([]int, len(pattern))
	prefixLength := 0

	for i := 1; i < len(pattern); i++ {
		for prefixLength > 0 && pattern[i] != pattern[prefixLength] {
			prefixLength = failure[prefixLength-1]
		}
		if pattern[i] == pattern[prefixLength] {
			prefixLength++
		}
		failure[i] = prefixLength
	}

	return failure
}

// kmpSearch returns all rune start indices where pattern occurs in text.
// An empty pattern matches nowhere by convention here.
func kmpSearch(text, pattern string) []int {
	patternRunes := []rune(pattern)
	if len(patternRunes) == 0 {
		return nil
	}

	failure := buildFailureTable(patternRunes)
	var matches []int
	matched := 0 // number of pattern runes currently matched

	for i, r := range []rune(text) {
		for matched > 0 && r != patternRunes[matched] {
			matched = failure[matched-1]
		}
		if r == patternRunes[matched] {
			matched++
		}
		if matched == len(patternRunes) {
			matches = append(matches, i-len(patternRunes)+1)
			matched = failure[matched-1]
		}
	}

	return matches
}

func intSlicesEqual(a, b []int) bool {
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

func main() {
	if got := kmpSearch("ababcababcabc", "abc"); !intSlicesEqual(got, []int{2, 7, 10}) {
		panic(fmt.Sprintf("expected [2 7 10], got %v", got))
	}
	// Overlapping matches.
	if got := kmpSearch("aaaaa", "aa"); !intSlicesEqual(got, []int{0, 1, 2, 3}) {
		panic(fmt.Sprintf("expected [0 1 2 3], got %v", got))
	}
	if got := kmpSearch("hello", "world"); len(got) != 0 {
		panic(fmt.Sprintf("expected no matches, got %v", got))
	}
	if got := kmpSearch("abc", ""); len(got) != 0 {
		panic(fmt.Sprintf("expected no matches, got %v", got))
	}
	if got := kmpSearch("abc", "abcd"); len(got) != 0 {
		panic(fmt.Sprintf("expected no matches, got %v", got))
	}
	if got := kmpSearch("abcabcabc", "abcabc"); !intSlicesEqual(got, []int{0, 3}) {
		panic(fmt.Sprintf("expected [0 3], got %v", got))
	}
	if got := buildFailureTable([]rune("abacaba")); !intSlicesEqual(got, []int{0, 0, 1, 0, 1, 2, 3}) {
		panic(fmt.Sprintf("expected [0 0 1 0 1 2 3], got %v", got))
	}
	fmt.Println("kmp-string-search: all tests passed")
}
