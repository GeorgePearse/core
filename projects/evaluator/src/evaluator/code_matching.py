"""Code matching and comparison utilities."""

import ast
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal, Optional


@dataclass
class MatchResult:
    """Result of comparing two code snippets."""

    matched: bool
    """Whether the snippets match at the specified level."""

    score: float
    """Match score from 0 to 1."""

    message: str
    """Human-readable explanation of the result."""

    details: Optional[dict] = None
    """Additional debugging information."""


class AbstractCodeMatcher(ABC):
    """Base class for language-specific code matchers."""

    language: str
    """Programming language this matcher handles."""

    @abstractmethod
    def match_exact(self, expected: str, actual: str) -> MatchResult:
        """Check for exact string match.

        Args:
            expected: Expected code snippet.
            actual: Actual code snippet.

        Returns:
            MatchResult indicating if code matches exactly.
        """
        pass

    @abstractmethod
    def match_semantic(self, expected: str, actual: str) -> MatchResult:
        """Check for semantic equivalence (AST-based).

        Args:
            expected: Expected code snippet.
            actual: Actual code snippet.

        Returns:
            MatchResult indicating semantic equivalence.
        """
        pass

    @abstractmethod
    def match_regex(self, pattern: str, actual: str) -> MatchResult:
        """Check if code matches regex pattern.

        Args:
            pattern: Regex pattern to match.
            actual: Code to search in.

        Returns:
            MatchResult indicating if pattern is found.
        """
        pass

    def compare(
        self,
        expected: str,
        actual: str,
        match_type: Literal["exact", "semantic", "regex"] = "exact",
    ) -> MatchResult:
        """Compare code snippets at specified level.

        Args:
            expected: Expected code snippet (or regex pattern for "regex" type).
            actual: Actual code snippet.
            match_type: Type of matching to perform.

        Returns:
            MatchResult with detailed comparison output.
        """
        if match_type == "exact":
            return self.match_exact(expected, actual)
        elif match_type == "semantic":
            return self.match_semantic(expected, actual)
        elif match_type == "regex":
            return self.match_regex(expected, actual)
        else:
            return MatchResult(
                matched=False,
                score=0.0,
                message=f"Unknown match_type: {match_type}",
            )


class PythonASTMatcher(AbstractCodeMatcher):
    """Code matcher for Python using AST comparison."""

    language = "python"

    def match_exact(self, expected: str, actual: str) -> MatchResult:
        """Check for exact string match or substring containment.

        First checks for exact match (after normalization).
        If that fails, checks if expected is contained in actual (for snippet matching).
        """
        # Normalize whitespace
        expected_normalized = " ".join(expected.split())
        actual_normalized = " ".join(actual.split())

        # Check for exact match
        if expected_normalized == actual_normalized:
            return MatchResult(
                matched=True,
                score=1.0,
                message="Exact match (after whitespace normalization)",
            )

        # Check for substring containment (useful for code snippet matching)
        if expected_normalized in actual_normalized:
            return MatchResult(
                matched=True,
                score=0.95,  # Slightly lower than exact match
                message="Code snippet found in output (substring match)",
            )

        return MatchResult(
            matched=False,
            score=0.0,
            message="Code does not match exactly",
            details={
                "expected": expected_normalized[:100],
                "actual": actual_normalized[:100],
            },
        )

    def match_semantic(self, expected: str, actual: str) -> MatchResult:
        """Check for AST-based semantic equivalence."""
        try:
            expected_ast = ast.parse(expected)
            actual_ast = ast.parse(actual)
        except SyntaxError as e:
            return MatchResult(
                matched=False,
                score=0.0,
                message=f"Syntax error in code: {e}",
                details={"error": str(e)},
            )

        # Compare ASTs
        similarity = self._ast_similarity(expected_ast, actual_ast)

        if similarity >= 0.75:  # Default threshold
            return MatchResult(
                matched=True,
                score=similarity,
                message=f"Semantic match with {similarity*100:.1f}% similarity",
            )

        return MatchResult(
            matched=False,
            score=similarity,
            message=f"Semantic similarity {similarity*100:.1f}% below threshold (75%)",
            details={"similarity_score": similarity},
        )

    def match_regex(self, pattern: str, actual: str) -> MatchResult:
        """Check if code matches regex pattern."""
        try:
            if re.search(pattern, actual):
                return MatchResult(
                    matched=True,
                    score=1.0,
                    message=f"Pattern found: {pattern}",
                )
            else:
                return MatchResult(
                    matched=False,
                    score=0.0,
                    message=f"Pattern not found: {pattern}",
                )
        except re.error as e:
            return MatchResult(
                matched=False,
                score=0.0,
                message=f"Invalid regex pattern: {e}",
                details={"error": str(e)},
            )

    def _ast_similarity(self, expected_tree: ast.AST, actual_tree: ast.AST) -> float:
        """Calculate similarity between two AST trees (0-1).

        Uses a simple node-counting approach. More sophisticated approaches
        could use tree edit distance, but this is sufficient for MVP.

        Args:
            expected_tree: Expected AST.
            actual_tree: Actual AST.

        Returns:
            Similarity score from 0 to 1.
        """
        expected_nodes = self._ast_to_string(expected_tree)
        actual_nodes = self._ast_to_string(actual_tree)

        # Simple comparison: count matching nodes
        matching_nodes = sum(1 for e, a in zip(expected_nodes, actual_nodes) if e == a)
        total_nodes = max(len(expected_nodes), len(actual_nodes))

        if total_nodes == 0:
            return 1.0

        return matching_nodes / total_nodes

    @staticmethod
    def _ast_to_string(tree: ast.AST) -> list[str]:
        """Convert AST to list of node type strings for comparison.

        Args:
            tree: AST to convert.

        Returns:
            List of node type names in traversal order.
        """
        nodes = []

        for node in ast.walk(tree):
            nodes.append(node.__class__.__name__)

        return nodes


# Registry of matchers by language
_MATCHERS: dict[str, type[AbstractCodeMatcher]] = {
    "python": PythonASTMatcher,
}


def get_matcher(language: str) -> AbstractCodeMatcher:
    """Get a code matcher for the specified language.

    Args:
        language: Programming language name (e.g., 'python').

    Returns:
        Matcher instance for the language.

    Raises:
        ValueError: If language is not supported.
    """
    if language not in _MATCHERS:
        raise ValueError(
            f"Unsupported language: {language}. " f"Supported: {list(_MATCHERS.keys())}"
        )

    return _MATCHERS[language]()


def register_matcher(language: str, matcher_class: type[AbstractCodeMatcher]) -> None:
    """Register a custom code matcher for a language.

    Args:
        language: Programming language name.
        matcher_class: Matcher class to register.
    """
    _MATCHERS[language] = matcher_class
