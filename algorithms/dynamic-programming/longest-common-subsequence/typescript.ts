/**
 * Longest Common Subsequence (LCS).
 *
 * Computes the longest subsequence (in-order, not necessarily contiguous)
 * common to two strings, returning the subsequence itself by backtracking
 * through the DP table.
 *
 * Time complexity:  O(m * n)
 * Space complexity: O(m * n)
 */

/**
 * Return the longest common subsequence of `first` and `second`.
 * dp[i][j] holds the LCS length of first.slice(0, i) and second.slice(0, j).
 */
function longestCommonSubsequence(first: string, second: string): string {
  const m = first.length;
  const n = second.length;

  const dp: number[][] = Array.from({ length: m + 1 }, () =>
    new Array<number>(n + 1).fill(0),
  );

  for (let i = 1; i <= m; i++) {
    for (let j = 1; j <= n; j++) {
      if (first[i - 1] === second[j - 1]) {
        dp[i][j] = dp[i - 1][j - 1] + 1;
      } else {
        dp[i][j] = Math.max(dp[i - 1][j], dp[i][j - 1]);
      }
    }
  }

  // Backtrack from dp[m][n] to reconstruct the subsequence.
  const result: string[] = [];
  let i = m;
  let j = n;
  while (i > 0 && j > 0) {
    if (first[i - 1] === second[j - 1]) {
      result.push(first[i - 1]);
      i--;
      j--;
    } else if (dp[i - 1][j] >= dp[i][j - 1]) {
      i--;
    } else {
      j--;
    }
  }

  return result.reverse().join("");
}

function main(): void {
  console.assert(longestCommonSubsequence("ABCBDAB", "BDCABA") === "BCBA");
  console.assert(longestCommonSubsequence("AGGTAB", "GXTXAYB") === "GTAB");
  console.assert(longestCommonSubsequence("", "ABC") === "");
  console.assert(longestCommonSubsequence("ABC", "ABC") === "ABC");
  console.assert(longestCommonSubsequence("ABC", "XYZ") === "");
  console.log("longest-common-subsequence: all tests passed");
}

main();
