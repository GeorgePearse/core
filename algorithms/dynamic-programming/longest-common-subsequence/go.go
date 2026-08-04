// Longest Common Subsequence (LCS).
//
// Computes the longest subsequence (in-order, not necessarily contiguous)
// common to two strings, returning the subsequence itself by backtracking
// through the DP table.
//
// Time complexity:  O(m * n)
// Space complexity: O(m * n)
package main

import "fmt"

// longestCommonSubsequence returns the longest common subsequence of
// first and second. dp[i][j] holds the LCS length of the first i runes
// of first and the first j runes of second.
func longestCommonSubsequence(first, second string) string {
	a := []rune(first)
	b := []rune(second)
	m, n := len(a), len(b)

	dp := make([][]int, m+1)
	for i := range dp {
		dp[i] = make([]int, n+1)
	}

	for i := 1; i <= m; i++ {
		for j := 1; j <= n; j++ {
			if a[i-1] == b[j-1] {
				dp[i][j] = dp[i-1][j-1] + 1
			} else if dp[i-1][j] >= dp[i][j-1] {
				dp[i][j] = dp[i-1][j]
			} else {
				dp[i][j] = dp[i][j-1]
			}
		}
	}

	// Backtrack from dp[m][n] to reconstruct the subsequence.
	result := make([]rune, 0, dp[m][n])
	i, j := m, n
	for i > 0 && j > 0 {
		switch {
		case a[i-1] == b[j-1]:
			result = append(result, a[i-1])
			i--
			j--
		case dp[i-1][j] >= dp[i][j-1]:
			i--
		default:
			j--
		}
	}

	// Reverse in place: the backtrack collected runes back-to-front.
	for left, right := 0, len(result)-1; left < right; left, right = left+1, right-1 {
		result[left], result[right] = result[right], result[left]
	}
	return string(result)
}

func main() {
	if got := longestCommonSubsequence("ABCBDAB", "BDCABA"); got != "BCBA" {
		panic("expected BCBA, got " + got)
	}
	if got := longestCommonSubsequence("AGGTAB", "GXTXAYB"); got != "GTAB" {
		panic("expected GTAB, got " + got)
	}
	if got := longestCommonSubsequence("", "ABC"); got != "" {
		panic("expected empty string, got " + got)
	}
	if got := longestCommonSubsequence("ABC", "ABC"); got != "ABC" {
		panic("expected ABC, got " + got)
	}
	if got := longestCommonSubsequence("ABC", "XYZ"); got != "" {
		panic("expected empty string, got " + got)
	}
	fmt.Println("longest-common-subsequence: all tests passed")
}
