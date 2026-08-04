"""Longest Common Subsequence (LCS).

Computes the longest subsequence (in-order, not necessarily contiguous)
common to two strings, returning the subsequence itself by backtracking
through the DP table.

Time complexity:  O(m * n)
Space complexity: O(m * n)
"""


def longest_common_subsequence(first: str, second: str) -> str:
    """Return the longest common subsequence of `first` and `second`.

    dp[i][j] holds the LCS length of first[:i] and second[:j].
    """
    m, n = len(first), len(second)
    dp: list[list[int]] = [[0] * (n + 1) for _ in range(m + 1)]

    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if first[i - 1] == second[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])

    # Backtrack from dp[m][n] to reconstruct the subsequence.
    result: list[str] = []
    i, j = m, n
    while i > 0 and j > 0:
        if first[i - 1] == second[j - 1]:
            result.append(first[i - 1])
            i -= 1
            j -= 1
        elif dp[i - 1][j] >= dp[i][j - 1]:
            i -= 1
        else:
            j -= 1

    return "".join(reversed(result))


if __name__ == "__main__":
    assert longest_common_subsequence("ABCBDAB", "BDCABA") == "BCBA"
    assert longest_common_subsequence("AGGTAB", "GXTXAYB") == "GTAB"
    assert longest_common_subsequence("", "ABC") == ""
    assert longest_common_subsequence("ABC", "ABC") == "ABC"
    assert longest_common_subsequence("ABC", "XYZ") == ""
    print("longest-common-subsequence: all tests passed")
