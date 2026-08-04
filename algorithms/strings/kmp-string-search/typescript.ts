/**
 * Knuth-Morris-Pratt (KMP) string search.
 *
 * Finds all start indices where a pattern occurs in a text. Precomputes a
 * failure table (length of the longest proper prefix of the pattern that
 * is also a suffix) so the text pointer never moves backwards.
 *
 * Time complexity:  O(n + m) where n = text.length, m = pattern.length
 * Space complexity: O(m) for the failure table
 */

/**
 * Return the KMP failure table for `pattern`.
 * failure[i] is the length of the longest proper prefix of
 * pattern.slice(0, i + 1) that is also a suffix of it.
 */
function buildFailureTable(pattern: string): number[] {
  const failure: number[] = new Array<number>(pattern.length).fill(0);
  let prefixLength = 0;

  for (let i = 1; i < pattern.length; i++) {
    while (prefixLength > 0 && pattern[i] !== pattern[prefixLength]) {
      prefixLength = failure[prefixLength - 1];
    }
    if (pattern[i] === pattern[prefixLength]) {
      prefixLength++;
    }
    failure[i] = prefixLength;
  }

  return failure;
}

/**
 * Return all start indices where `pattern` occurs in `text`.
 * An empty pattern matches nowhere by convention here.
 */
function kmpSearch(text: string, pattern: string): number[] {
  if (pattern.length === 0) {
    return [];
  }

  const failure = buildFailureTable(pattern);
  const matches: number[] = [];
  let matched = 0; // number of pattern characters currently matched

  for (let i = 0; i < text.length; i++) {
    while (matched > 0 && text[i] !== pattern[matched]) {
      matched = failure[matched - 1];
    }
    if (text[i] === pattern[matched]) {
      matched++;
    }
    if (matched === pattern.length) {
      matches.push(i - pattern.length + 1);
      matched = failure[matched - 1];
    }
  }

  return matches;
}

function arraysEqual(a: number[], b: number[]): boolean {
  return a.length === b.length && a.every((value, index) => value === b[index]);
}

function main(): void {
  console.assert(arraysEqual(kmpSearch("ababcababcabc", "abc"), [2, 7, 10]));
  console.assert(arraysEqual(kmpSearch("aaaaa", "aa"), [0, 1, 2, 3])); // overlapping
  console.assert(arraysEqual(kmpSearch("hello", "world"), []));
  console.assert(arraysEqual(kmpSearch("abc", ""), []));
  console.assert(arraysEqual(kmpSearch("abc", "abcd"), []));
  console.assert(arraysEqual(kmpSearch("abcabcabc", "abcabc"), [0, 3]));
  console.assert(arraysEqual(buildFailureTable("abacaba"), [0, 0, 1, 0, 1, 2, 3]));
  console.log("kmp-string-search: all tests passed");
}

main();
