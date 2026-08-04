"""Edit distance (Levenshtein distance).

Computes the minimum number of single-character insertions, deletions,
and substitutions (all unit cost) needed to transform one string into
another, using the classic bottom-up DP table.

Time complexity:  O(m * n)
Space complexity: O(m * n)
"""


def edit_distance(source: str, target: str) -> int:
    """Return the Levenshtein distance between `source` and `target`.

    dp[i][j] holds the edit distance between source[:i] and target[:j].
    """
    m, n = len(source), len(target)
    dp: list[list[int]] = [[0] * (n + 1) for _ in range(m + 1)]

    # Transforming a prefix into the empty string takes i deletions,
    # and the empty string into a prefix takes j insertions.
    for i in range(m + 1):
        dp[i][0] = i
    for j in range(n + 1):
        dp[0][j] = j

    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if source[i - 1] == target[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]
            else:
                dp[i][j] = 1 + min(
                    dp[i - 1][j],      # delete source[i - 1]
                    dp[i][j - 1],      # insert target[j - 1]
                    dp[i - 1][j - 1],  # substitute
                )

    return dp[m][n]


if __name__ == "__main__":
    assert edit_distance("kitten", "sitting") == 3
    assert edit_distance("flaw", "lawn") == 2
    assert edit_distance("", "abc") == 3
    assert edit_distance("abc", "") == 3
    assert edit_distance("same", "same") == 0
    assert edit_distance("intention", "execution") == 5
    print("edit-distance: all tests passed")
