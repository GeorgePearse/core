"""Parser for unified diff format."""

import re
from typing import Optional

from evaluator.diff_models import (
    DiffHunk,
    DiffLine,
    DiffLineType,
    DiffValidationResult,
    FileDiff,
    GitDiff,
)


class DiffParser:
    """Parser for unified diff format (git diff output)."""

    # Regex patterns for parsing
    DIFF_HEADER = re.compile(r"^diff --git a/(.+) b/(.+)$")
    OLD_FILE = re.compile(r"^--- (?:a/)?(.+)$")
    NEW_FILE = re.compile(r"^\+\+\+ (?:b/)?(.+)$")
    HUNK_HEADER = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)$")
    NEW_FILE_MODE = re.compile(r"^new file mode (\d+)$")
    DELETED_FILE_MODE = re.compile(r"^deleted file mode (\d+)$")
    OLD_MODE = re.compile(r"^old mode (\d+)$")
    NEW_MODE = re.compile(r"^new mode (\d+)$")
    RENAME_FROM = re.compile(r"^rename from (.+)$")
    RENAME_TO = re.compile(r"^rename to (.+)$")
    BINARY_FILE = re.compile(r"^Binary files .+ and .+ differ$")
    INDEX_LINE = re.compile(r"^index [a-f0-9]+\.\.[a-f0-9]+")

    def parse(self, diff_text: str) -> GitDiff:
        """Parse a unified diff string into a GitDiff object.

        Args:
            diff_text: Raw diff text (git diff output)

        Returns:
            Parsed GitDiff object
        """
        git_diff = GitDiff(raw_diff=diff_text)
        lines = diff_text.split("\n")

        current_file: Optional[FileDiff] = None
        current_hunk: Optional[DiffHunk] = None
        old_line_no = 0
        new_line_no = 0

        i = 0
        while i < len(lines):
            line = lines[i]

            # Check for diff header (start of new file diff)
            header_match = self.DIFF_HEADER.match(line)
            if header_match:
                # Save previous file if exists
                if current_file is not None:
                    if current_hunk is not None:
                        current_file.hunks.append(current_hunk)
                    git_diff.files.append(current_file)

                current_file = FileDiff(
                    old_path=header_match.group(1),
                    new_path=header_match.group(2),
                )
                current_hunk = None
                i += 1
                continue

            # Handle metadata lines for current file
            if current_file is not None:
                # New file mode
                new_mode_match = self.NEW_FILE_MODE.match(line)
                if new_mode_match:
                    current_file.is_new_file = True
                    current_file.new_mode = new_mode_match.group(1)
                    i += 1
                    continue

                # Deleted file mode
                del_mode_match = self.DELETED_FILE_MODE.match(line)
                if del_mode_match:
                    current_file.is_deleted_file = True
                    current_file.old_mode = del_mode_match.group(1)
                    i += 1
                    continue

                # Old mode
                old_mode_match = self.OLD_MODE.match(line)
                if old_mode_match:
                    current_file.old_mode = old_mode_match.group(1)
                    i += 1
                    continue

                # New mode
                new_mode_match = self.NEW_MODE.match(line)
                if new_mode_match:
                    current_file.new_mode = new_mode_match.group(1)
                    i += 1
                    continue

                # Rename detection
                rename_from_match = self.RENAME_FROM.match(line)
                if rename_from_match:
                    current_file.is_renamed = True
                    current_file.old_path = rename_from_match.group(1)
                    i += 1
                    continue

                rename_to_match = self.RENAME_TO.match(line)
                if rename_to_match:
                    current_file.new_path = rename_to_match.group(1)
                    i += 1
                    continue

                # Binary file
                if self.BINARY_FILE.match(line):
                    current_file.is_binary = True
                    i += 1
                    continue

                # Index line (skip)
                if self.INDEX_LINE.match(line):
                    i += 1
                    continue

            # Old file path (--- line)
            old_file_match = self.OLD_FILE.match(line)
            if old_file_match:
                path = old_file_match.group(1)
                if path != "/dev/null":
                    if current_file is not None:
                        current_file.old_path = path
                    else:
                        current_file = FileDiff(old_path=path)
                elif current_file is not None:
                    current_file.is_new_file = True
                i += 1
                continue

            # New file path (+++ line)
            new_file_match = self.NEW_FILE.match(line)
            if new_file_match:
                path = new_file_match.group(1)
                if path != "/dev/null":
                    if current_file is not None:
                        current_file.new_path = path
                    else:
                        current_file = FileDiff(new_path=path)
                elif current_file is not None:
                    current_file.is_deleted_file = True
                i += 1
                continue

            # Hunk header (@@ line)
            hunk_match = self.HUNK_HEADER.match(line)
            if hunk_match:
                # Save previous hunk if exists
                if current_hunk is not None and current_file is not None:
                    current_file.hunks.append(current_hunk)

                old_start = int(hunk_match.group(1))
                old_count = int(hunk_match.group(2)) if hunk_match.group(2) else 1
                new_start = int(hunk_match.group(3))
                new_count = int(hunk_match.group(4)) if hunk_match.group(4) else 1

                current_hunk = DiffHunk(
                    old_start=old_start,
                    old_count=old_count,
                    new_start=new_start,
                    new_count=new_count,
                    header=line,
                )

                old_line_no = old_start
                new_line_no = new_start
                i += 1
                continue

            # Diff content lines
            if current_hunk is not None:
                if line.startswith("+") and not line.startswith("+++"):
                    current_hunk.lines.append(
                        DiffLine(
                            type=DiffLineType.ADDITION,
                            content=line[1:],
                            new_line_no=new_line_no,
                        )
                    )
                    new_line_no += 1
                elif line.startswith("-") and not line.startswith("---"):
                    current_hunk.lines.append(
                        DiffLine(
                            type=DiffLineType.DELETION,
                            content=line[1:],
                            old_line_no=old_line_no,
                        )
                    )
                    old_line_no += 1
                elif line.startswith(" ") or line == "":
                    # Context line or empty line in diff
                    content = line[1:] if line.startswith(" ") else ""
                    current_hunk.lines.append(
                        DiffLine(
                            type=DiffLineType.CONTEXT,
                            content=content,
                            old_line_no=old_line_no,
                            new_line_no=new_line_no,
                        )
                    )
                    old_line_no += 1
                    new_line_no += 1
                elif line.startswith("\\"):
                    # "\ No newline at end of file" - skip
                    pass

            i += 1

        # Don't forget the last file and hunk
        if current_file is not None:
            if current_hunk is not None:
                current_file.hunks.append(current_hunk)
            git_diff.files.append(current_file)

        return git_diff

    def parse_from_response(self, response: str) -> Optional[GitDiff]:
        """Extract and parse a diff from an LLM response.

        Looks for diff content in code blocks or raw diff format.

        Args:
            response: Full LLM response text

        Returns:
            Parsed GitDiff or None if no diff found
        """
        # Try to find diff in code blocks first
        diff_patterns = [
            r"```diff\n(.*?)```",
            r"```\n(diff --git.*?)```",
            r"```patch\n(.*?)```",
        ]

        for pattern in diff_patterns:
            match = re.search(pattern, response, re.DOTALL)
            if match:
                return self.parse(match.group(1))

        # Try to find raw diff (starts with diff --git)
        diff_start = re.search(r"(diff --git .+?)(?=\n\n[^+-@ ]|\Z)", response, re.DOTALL)
        if diff_start:
            return self.parse(diff_start.group(1))

        # Try to find unified diff format (starts with ---)
        unified_start = re.search(
            r"(--- .+?\n\+\+\+ .+?\n@@.+?)(?=\n\n[^+-@ ]|\Z)", response, re.DOTALL
        )
        if unified_start:
            return self.parse(unified_start.group(1))

        return None


class DiffValidator:
    """Validates git diffs for correctness and applicability."""

    def validate_syntax(self, diff: GitDiff) -> DiffValidationResult:
        """Validate the syntactic correctness of a diff.

        Args:
            diff: Parsed GitDiff to validate

        Returns:
            DiffValidationResult with validation status
        """
        result = DiffValidationResult(is_valid=True)

        if not diff.files:
            result.add_error("Diff contains no file changes")
            return result

        for file_diff in diff.files:
            self._validate_file_diff(file_diff, result)

        return result

    def _validate_file_diff(self, file_diff: FileDiff, result: DiffValidationResult) -> None:
        """Validate a single file diff.

        Args:
            file_diff: The file diff to validate
            result: Result object to update
        """
        # Check for path
        if not file_diff.path:
            result.add_error("File diff missing path")

        # Check for at least one hunk (unless binary)
        if not file_diff.is_binary and not file_diff.hunks:
            result.add_warning(f"File {file_diff.path} has no hunks")

        # Validate each hunk
        for i, hunk in enumerate(file_diff.hunks):
            self._validate_hunk(hunk, file_diff.path, i, result)

    def _validate_hunk(
        self, hunk: DiffHunk, file_path: str, hunk_index: int, result: DiffValidationResult
    ) -> None:
        """Validate a single hunk.

        Args:
            hunk: The hunk to validate
            file_path: Path of the file containing this hunk
            hunk_index: Index of this hunk in the file
            result: Result object to update
        """
        # Count actual additions and deletions
        actual_additions = len(hunk.additions)
        actual_deletions = len(hunk.deletions)
        actual_context = len(hunk.context_lines)

        # Expected counts from header
        expected_old_lines = hunk.old_count
        expected_new_lines = hunk.new_count

        # Validate line counts
        actual_old_lines = actual_deletions + actual_context
        actual_new_lines = actual_additions + actual_context

        if actual_old_lines != expected_old_lines:
            result.add_warning(
                f"{file_path} hunk {hunk_index}: expected {expected_old_lines} old lines, "
                f"got {actual_old_lines}"
            )

        if actual_new_lines != expected_new_lines:
            result.add_warning(
                f"{file_path} hunk {hunk_index}: expected {expected_new_lines} new lines, "
                f"got {actual_new_lines}"
            )

    def validate_can_apply(
        self, diff: GitDiff, file_contents: dict[str, str]
    ) -> DiffValidationResult:
        """Check if a diff can be cleanly applied to given file contents.

        Args:
            diff: The diff to check
            file_contents: Dictionary mapping file paths to their current contents

        Returns:
            DiffValidationResult indicating if diff can be applied
        """
        result = DiffValidationResult(is_valid=True)

        for file_diff in diff.files:
            if file_diff.is_new_file:
                # New file - check it doesn't already exist
                if file_diff.path in file_contents:
                    result.add_error(f"Cannot create {file_diff.path}: file already exists")
                continue

            if file_diff.is_deleted_file:
                # Deleted file - check it exists
                if file_diff.old_path not in file_contents:
                    result.add_error(f"Cannot delete {file_diff.old_path}: file not found")
                continue

            # Modified file - check context matches
            path = file_diff.old_path or file_diff.path
            if path not in file_contents:
                result.add_error(f"Cannot modify {path}: file not found")
                continue

            content_lines = file_contents[path].split("\n")
            self._validate_hunks_apply(file_diff, content_lines, result)

        return result

    def _validate_hunks_apply(
        self, file_diff: FileDiff, content_lines: list[str], result: DiffValidationResult
    ) -> None:
        """Validate that hunks can be applied to file content.

        Args:
            file_diff: The file diff
            content_lines: Lines of the original file
            result: Result object to update
        """
        for hunk in file_diff.hunks:
            # Check that context and deleted lines match the original
            line_no = hunk.old_start - 1  # Convert to 0-based

            for diff_line in hunk.lines:
                if diff_line.type == DiffLineType.ADDITION:
                    continue  # Additions don't need to match

                if line_no >= len(content_lines):
                    result.add_error(
                        f"{file_diff.path}: hunk extends beyond file end at line {line_no + 1}"
                    )
                    return

                expected_content = diff_line.content
                actual_content = content_lines[line_no]

                if expected_content != actual_content:
                    result.add_error(
                        f"{file_diff.path} line {line_no + 1}: context mismatch\n"
                        f"  Expected: {expected_content!r}\n"
                        f"  Actual:   {actual_content!r}"
                    )

                line_no += 1


def extract_diff_from_response(response: str) -> Optional[GitDiff]:
    """Convenience function to extract and parse diff from LLM response.

    Args:
        response: Full LLM response text

    Returns:
        Parsed GitDiff or None if no diff found
    """
    parser = DiffParser()
    return parser.parse_from_response(response)
