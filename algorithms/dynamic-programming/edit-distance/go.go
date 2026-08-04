// Edit distance (Levenshtein distance).
//
// Computes the minimum number of single-character insertions, deletions,
// and substitutions (all unit cost) needed to transform one string into
// another, using the classic bottom-up DP table.
//
// Time complexity:  O(m * n)
// Space complexity: O(m * n)
package main

import "fmt"

// editDistance returns the Levenshtein distance between source and target.
// dp[i][j] holds the edit distance between the first i runes of source
// and the first j runes of target.
func editDistance(source, target string) int {
	a := []rune(source)
	b := []rune(target)
	m, n := len(a), len(b)

	dp := make([][]int, m+1)
	for i := range dp {
		dp[i] = make([]int, n+1)
	}

	// Transforming a prefix into the empty string takes i deletions,
	// and the empty string into a prefix takes j insertions.
	for i := 0; i <= m; i++ {
		dp[i][0] = i
	}
	for j := 0; j <= n; j++ {
		dp[0][j] = j
	}

	for i := 1; i <= m; i++ {
		for j := 1; j <= n; j++ {
			if a[i-1] == b[j-1] {
				dp[i][j] = dp[i-1][j-1]
				continue
			}
			best := dp[i-1][j] // delete source[i-1]
			if dp[i][j-1] < best {
				best = dp[i][j-1] // insert target[j-1]
			}
			if dp[i-1][j-1] < best {
				best = dp[i-1][j-1] // substitute
			}
			dp[i][j] = 1 + best
		}
	}

	return dp[m][n]
}

func main() {
	cases := []struct {
		source, target string
		want           int
	}{
		{"kitten", "sitting", 3},
		{"flaw", "lawn", 2},
		{"", "abc", 3},
		{"abc", "", 3},
		{"same", "same", 0},
		{"intention", "execution", 5},
	}
	for _, c := range cases {
		if got := editDistance(c.source, c.target); got != c.want {
			panic(fmt.Sprintf("editDistance(%q, %q) = %d, want %d", c.source, c.target, got, c.want))
		}
	}
	fmt.Println("edit-distance: all tests passed")
}
