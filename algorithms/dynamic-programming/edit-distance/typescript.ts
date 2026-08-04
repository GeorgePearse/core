/**
 * Edit distance (Levenshtein distance).
 *
 * Computes the minimum number of single-character insertions, deletions,
 * and substitutions (all unit cost) needed to transform one string into
 * another, using the classic bottom-up DP table.
 *
 * Time complexity:  O(m * n)
 * Space complexity: O(m * n)
 */

/**
 * Return the Levenshtein distance between `source` and `target`.
 * dp[i][j] holds the edit distance between source.slice(0, i) and
 * target.slice(0, j).
 */
function editDistance(source: string, target: string): number {
  const m = source.length;
  const n = target.length;

  const dp: number[][] = Array.from({ length: m + 1 }, () =>
    new Array<number>(n + 1).fill(0),
  );

  // Transforming a prefix into the empty string takes i deletions,
  // and the empty string into a prefix takes j insertions.
  for (let i = 0; i <= m; i++) dp[i][0] = i;
  for (let j = 0; j <= n; j++) dp[0][j] = j;

  for (let i = 1; i <= m; i++) {
    for (let j = 1; j <= n; j++) {
      if (source[i - 1] === target[j - 1]) {
        dp[i][j] = dp[i - 1][j - 1];
      } else {
        dp[i][j] =
          1 +
          Math.min(
            dp[i - 1][j], // delete source[i - 1]
            dp[i][j - 1], // insert target[j - 1]
            dp[i - 1][j - 1], // substitute
          );
      }
    }
  }

  return dp[m][n];
}

function main(): void {
  console.assert(editDistance("kitten", "sitting") === 3);
  console.assert(editDistance("flaw", "lawn") === 2);
  console.assert(editDistance("", "abc") === 3);
  console.assert(editDistance("abc", "") === 3);
  console.assert(editDistance("same", "same") === 0);
  console.assert(editDistance("intention", "execution") === 5);
  console.log("edit-distance: all tests passed");
}

main();
