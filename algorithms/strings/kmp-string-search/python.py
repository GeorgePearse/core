"""Knuth-Morris-Pratt (KMP) string search.

Finds all start indices where a pattern occurs in a text. Precomputes a
failure table (length of the longest proper prefix of the pattern that
is also a suffix) so the text pointer never moves backwards.

Time complexity:  O(n + m) where n = len(text), m = len(pattern)
Space complexity: O(m) for the failure table
"""


def build_failure_table(pattern: str) -> list[int]:
    """Return the KMP failure table for `pattern`.

    failure[i] is the length of the longest proper prefix of
    pattern[: i + 1] that is also a suffix of it.
    """
    failure: list[int] = [0] * len(pattern)
    prefix_length = 0

    for i in range(1, len(pattern)):
        while prefix_length > 0 and pattern[i] != pattern[prefix_length]:
            prefix_length = failure[prefix_length - 1]
        if pattern[i] == pattern[prefix_length]:
            prefix_length += 1
        failure[i] = prefix_length

    return failure


def kmp_search(text: str, pattern: str) -> list[int]:
    """Return all start indices where `pattern` occurs in `text`.

    An empty pattern matches nowhere by convention here.
    """
    if not pattern:
        return []

    failure = build_failure_table(pattern)
    matches: list[int] = []
    matched = 0  # number of pattern characters currently matched

    for i, char in enumerate(text):
        while matched > 0 and char != pattern[matched]:
            matched = failure[matched - 1]
        if char == pattern[matched]:
            matched += 1
        if matched == len(pattern):
            matches.append(i - len(pattern) + 1)
            matched = failure[matched - 1]

    return matches


if __name__ == "__main__":
    assert kmp_search("ababcababcabc", "abc") == [2, 7, 10]
    assert kmp_search("aaaaa", "aa") == [0, 1, 2, 3]  # overlapping matches
    assert kmp_search("hello", "world") == []
    assert kmp_search("abc", "") == []
    assert kmp_search("abc", "abcd") == []
    assert kmp_search("abcabcabc", "abcabc") == [0, 3]
    assert build_failure_table("abacaba") == [0, 0, 1, 0, 1, 2, 3]
    print("kmp-string-search: all tests passed")
