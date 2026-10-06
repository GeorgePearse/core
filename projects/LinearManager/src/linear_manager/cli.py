"""Command line entrypoints for LinearManager."""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path
from typing import Iterable


try:  # pragma: no cover - fallback when colorama is absent
    from colorama import Fore, Style, init
except ImportError:  # pragma: no cover - fallback used in minimal environments

    class _Color:
        BLACK = BLUE = CYAN = GREEN = MAGENTA = RED = WHITE = YELLOW = ""
        RESET = ""

    class _Style:
        BRIGHT = RESET_ALL = ""

    def init(*_: object, **__: object) -> None:
        return None

    Fore = _Color()  # type: ignore
    Style = _Style()  # type: ignore

from linear_manager.operations import (
    IssueSpec,
    PushConfig,
    load_manifest,
    run_push,
    run_pull,
)
from . import config

# Initialize colorama
init(autoreset=True)

ANSI_ESCAPE_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")


def _strip_ansi(text: str) -> str:
    return ANSI_ESCAPE_RE.sub("", text)


def _visible_length(text: str) -> int:
    return len(_strip_ansi(text))


def _ljust_visible(text: str, width: int) -> str:
    padding = max(width - _visible_length(text), 0)
    return text + (" " * padding)


def _status_color(status: str) -> str:
    """Map a status string to a representative color."""
    mapping: dict[str, str] = {
        "pass": str(Fore.GREEN),
        "fail": str(Fore.RED),
        "pending": str(Fore.YELLOW),
        "skipped": str(Fore.BLUE),
        "cancelled": str(Fore.MAGENTA),
        "missing_branch": str(Fore.YELLOW),
        "gh_missing": str(Fore.RED),
        "parse_error": str(Fore.RED),
        "error": str(Fore.RED),
        "no_checks": str(Fore.CYAN),
        "unknown": str(Fore.CYAN),
    }
    return mapping.get(status.lower(), str(Fore.CYAN))


def _get_tasks_directory() -> Path:
    """Get the tasks directory for LinearManager.

    Uses LINEAR_MANAGER_HOME environment variable if set,
    otherwise defaults to ~/LinearManager/tasks.
    """
    return config.get_tasks_directory()


def _discover_manifest_files(path: Path) -> list[Path]:
    if path.is_dir():
        files = sorted(
            {
                candidate
                for pattern in ("*.yaml", "*.yml")
                for candidate in path.rglob(pattern)
                if candidate.is_file()
            }
        )
        return files
    if path.is_file():
        if path.suffix.lower() not in {".yaml", ".yml"}:
            raise RuntimeError(f"Manifest file {path} must be .yaml or .yml.")
        return [path]
    raise RuntimeError(f"Manifest path {path} does not exist.")


def _format_branch_description(issue: IssueSpec, verbose: bool = False) -> str:
    branch = issue.branch or ""
    if not verbose:
        return branch
    description = (issue.description or "").strip()
    first_line = description.splitlines()[0] if description else ""
    if branch and first_line:
        return f"{branch} - {first_line}"
    return branch or first_line


def _format_status(issue: IssueSpec) -> str:
    state = (issue.state or "").strip()
    state_key = state.lower()

    todo_states = {
        "todo",
        "to do",
        "backlog",
        "triage",
        "planned",
        "ready",
    }
    in_progress_states = {
        "in progress",
        "wip",
        "doing",
        "progress",
        "started",
        "working",
    }
    review_states = {
        "review",
        "in review",
        "feedback",
        "blocked",
        "qa",
        "testing",
    }
    done_states = {
        "done",
        "completed",
        "complete",
        "closed",
        "resolved",
    }
    cancelled_states = {
        "canceled",
        "cancelled",
        "abandoned",
        "declined",
    }

    symbol = "·"
    color = Fore.WHITE
    label_hint = state

    if state_key in done_states:
        symbol = "[x]"
        color = Fore.GREEN
        label_hint = state or "Complete"
    elif state_key in cancelled_states:
        symbol = "✖"
        color = Fore.RED
        label_hint = state or "Cancelled"
    elif state_key in in_progress_states:
        symbol = "→"
        color = Fore.CYAN
        label_hint = state or "In Progress"
    elif state_key in review_states:
        symbol = "⧖"
        color = Fore.MAGENTA
        label_hint = state or "Review"
    elif not state:
        symbol = "[ ]"
        color = Fore.YELLOW
        label_hint = "No state"
    elif state_key in todo_states:
        symbol = "[ ]"
        color = Fore.YELLOW
        label_hint = state or "Todo"
    else:
        symbol = "○"
        color = Fore.BLUE
        label_hint = state

    parts: list[str] = [f"{color}{Style.BRIGHT}{symbol}{Style.RESET_ALL}"]
    if label_hint:
        parts.append(f"{Style.DIM}{label_hint}{Style.RESET_ALL}")
    if issue.blocked_by:
        blocked_str = ", ".join(issue.blocked_by)
        parts.append(
            f"{Fore.RED}{Style.BRIGHT}🚫{Style.RESET_ALL} {Style.DIM}Blocked by: {blocked_str}{Style.RESET_ALL}"
        )
    return " ".join(parts)


def _wrap_text(text: str, max_width: int) -> list[str]:
    """Wrap text to fit within max_width, breaking on word boundaries."""
    if not text:
        return [""]

    words = text.split()
    lines: list[str] = []
    current_line: list[str] = []
    current_length = 0

    for word in words:
        word_length = _visible_length(word)
        # Account for space before word (except for first word on line)
        needed_length = word_length + (1 if current_line else 0)

        if current_length + needed_length <= max_width:
            current_line.append(word)
            current_length += needed_length
        else:
            # Start new line
            if current_line:
                lines.append(" ".join(current_line))
            # Handle words longer than max_width by breaking them
            if word_length > max_width:
                if "\x1b" in word:
                    lines.append(word)
                else:
                    for i in range(0, len(word), max_width):
                        lines.append(word[i : i + max_width])
                current_line = []
                current_length = 0
            else:
                current_line = [word]
                current_length = word_length

    if current_line:
        lines.append(" ".join(current_line))

    return lines if lines else [""]


def _table_lines(headers: list[str], rows: Iterable[list[str]]) -> list[str]:
    # Get terminal width, defaulting to 120 if unable to determine
    terminal_width = shutil.get_terminal_size(fallback=(120, 24)).columns

    # Reserve space for borders and separators (3 chars per column + 4 for borders)
    num_columns = len(headers)
    separator_space = (num_columns * 3) + 4
    available_width = max(
        terminal_width - separator_space, num_columns * 5
    )  # At least 5 chars per column

    # Define relative weights for each column based on typical content size
    # These weights determine how much of the available width each column gets
    column_weights_map = {
        8: [25, 8, 15, 20, 20, 25, 30, 15],  # Full view with description
        7: [25, 8, 15, 20, 20, 30, 18],  # Compact view without description
    }

    column_weights = column_weights_map.get(
        num_columns, [100 // num_columns] * num_columns
    )
    total_weight = sum(column_weights)

    # Calculate actual column widths based on available space and weights
    max_column_widths = [
        max(5, int(available_width * weight / total_weight))
        for weight in column_weights
    ]

    # Wrap text in all cells and split into lines
    split_rows: list[list[list[str]]] = []
    for row in [headers] + list(rows):
        wrapped_row: list[list[str]] = []
        for idx, cell in enumerate(row):
            max_width = max_column_widths[idx] if idx < len(max_column_widths) else 40
            # First split on existing newlines, then wrap each line
            cell_lines: list[str] = []
            for line in cell.splitlines() or [""]:
                cell_lines.extend(_wrap_text(line, max_width))
            wrapped_row.append(cell_lines)
        split_rows.append(wrapped_row)

    column_count = len(headers)
    widths: list[int] = [0] * column_count
    for row_cells in split_rows:
        for idx, cell_lines in enumerate(row_cells):
            widths[idx] = max(
                widths[idx],
                *(_visible_length(line) for line in cell_lines),
            )

    def build_rule(char: str, color: str = str(Fore.CYAN)) -> str:
        rule = "+" + "+".join(char * (width + 2) for width in widths) + "+"
        return f"{color}{rule}{Style.RESET_ALL}"

    def render_row(cell_lines: list[list[str]], is_header: bool = False) -> list[str]:
        height = max(len(lines) for lines in cell_lines)
        rendered: list[str] = []
        for line_idx in range(height):
            parts: list[str] = []
            for col_idx, lines in enumerate(cell_lines):
                text = lines[line_idx] if line_idx < len(lines) else ""
                padded = _ljust_visible(text, widths[col_idx])
                if is_header:
                    parts.append(
                        f"{Fore.YELLOW}{Style.BRIGHT}{padded}{Style.RESET_ALL}"
                    )
                else:
                    parts.append(padded)
            rendered.append(
                f"{Fore.CYAN}|{Style.RESET_ALL} "
                + f" {Fore.CYAN}|{Style.RESET_ALL} ".join(parts)
                + f" {Fore.CYAN}|{Style.RESET_ALL}"
            )
        return rendered

    all_lines: list[str] = [build_rule("-")]
    all_lines.extend(render_row(split_rows[0], is_header=True))
    all_lines.append(build_rule("=", str(Fore.CYAN)))
    for row_cells in split_rows[1:]:
        all_lines.extend(render_row(row_cells))
    all_lines.append(build_rule("-"))
    return all_lines


def _render_issue_table(issues: list[IssueSpec], verbose: bool = False) -> str:
    if verbose:
        headers = [
            "Title",
            "Team",
            "Project",
            "Labels",
            "Branch",
            "Description",
            "Status",
        ]
        rows = [
            [
                f"• {issue.title}",
                issue.team_key or "",
                issue.project_name or "",
                ", ".join(issue.labels) if issue.labels else "",
                issue.branch or "",
                (issue.description or "").strip().splitlines()[0]
                if issue.description
                else "",
                _format_status(issue),
            ]
            for issue in issues
        ]
    else:
        headers = ["Title", "Team", "Project", "Labels", "Branch", "Status"]
        rows = [
            [
                f"• {issue.title}",
                issue.team_key or "",
                issue.project_name or "",
                ", ".join(issue.labels) if issue.labels else "",
                issue.branch or "",
                _format_status(issue),
            ]
            for issue in issues
        ]
    return "\n".join(_table_lines(headers, rows))


def _render_by_project(issues: list[IssueSpec]) -> str:
    """Render issues grouped by project."""
    from collections import defaultdict

    # Group issues by project
    projects: dict[str, list[IssueSpec]] = defaultdict(list)
    for issue in issues:
        project_name = issue.project_name or "(No Project)"
        projects[project_name].append(issue)

    # Sort projects: tickets with projects first (alphabetically), then "(No Project)" last
    def project_sort_key(project_name: str) -> tuple[int, str]:
        if project_name == "(No Project)":
            return (1, project_name)  # "(No Project)" goes last
        return (0, project_name)  # Real projects go first, sorted alphabetically

    sorted_projects = sorted(projects.keys(), key=project_sort_key)

    output_lines: list[str] = []
    for project_name in sorted_projects:
        project_issues = projects[project_name]

        # Project header with count
        header = f"\n{Fore.CYAN}{Style.BRIGHT}# {project_name}{Style.RESET_ALL} {Fore.YELLOW}({len(project_issues)} ticket{'s' if len(project_issues) != 1 else ''}){Style.RESET_ALL}"
        output_lines.append(header)
        output_lines.append("")

        # Sort issues by status (in progress first, then todo, then done)
        def sort_key(issue: IssueSpec) -> tuple[int, str]:
            state = (issue.state or "").lower()
            if state in {
                "in progress",
                "wip",
                "doing",
                "progress",
                "started",
                "working",
            }:
                priority = 0
            elif state in {"todo", "to do", "backlog", "triage", "planned", "ready"}:
                priority = 1
            elif state in {
                "review",
                "in review",
                "feedback",
                "blocked",
                "qa",
                "testing",
            }:
                priority = 2
            elif state in {"done", "completed", "complete", "closed", "resolved"}:
                priority = 3
            elif state in {"canceled", "cancelled", "abandoned", "declined"}:
                priority = 4
            else:
                priority = 5
            return (priority, issue.title or "")

        sorted_issues = sorted(project_issues, key=sort_key)

        # Render each issue as a bullet point
        for issue in sorted_issues:
            status = _format_status(issue)
            title = issue.title or "(Untitled)"

            # Build issue line with optional metadata
            parts = [f"  • {title}"]

            metadata: list[str] = []
            if issue.team_key:
                metadata.append(f"{Fore.MAGENTA}{issue.team_key}{Style.RESET_ALL}")
            if issue.branch:
                metadata.append(f"{Fore.BLUE}{issue.branch}{Style.RESET_ALL}")

            if metadata:
                parts.append(f"  {Style.DIM}({', '.join(metadata)}){Style.RESET_ALL}")

            parts.append(f"  {status}")

            issue_line = " ".join(parts)
            output_lines.append(issue_line)

        output_lines.append("")

    return "\n".join(output_lines)


def _render_by_block(issues: list[IssueSpec]) -> str:
    """Render issues grouped by blocking relationships."""
    # Build a map of issue titles to issues for quick lookup
    issue_map: dict[str, IssueSpec] = {issue.title: issue for issue in issues}

    # Find all blocking issues (those that are mentioned in blocked_by)
    blockers: set[str] = set()
    for issue in issues:
        blockers.update(issue.blocked_by)

    # Find issues that have blocked_by relationships
    blocked_issues: list[IssueSpec] = [issue for issue in issues if issue.blocked_by]

    if not blocked_issues:
        return f"{Fore.YELLOW}No blocking relationships found.{Style.RESET_ALL}\n"

    output_lines: list[str] = []
    output_lines.append(
        f"\n{Fore.CYAN}{Style.BRIGHT}# Blocking Relationships{Style.RESET_ALL}\n"
    )

    # Group blocked issues by their blockers
    from collections import defaultdict

    blocker_to_blocked: dict[str, list[IssueSpec]] = defaultdict(list)
    for issue in blocked_issues:
        for blocker in issue.blocked_by:
            blocker_to_blocked[blocker].append(issue)

    # Render each blocking relationship
    for blocker_title in sorted(blocker_to_blocked.keys()):
        blocked_list = blocker_to_blocked[blocker_title]

        # Check if the blocker is an actual ticket in our list
        blocker_issue = issue_map.get(blocker_title)

        # Render the blocker box
        output_lines.append(_render_box_for_issue(blocker_issue, blocker_title))
        output_lines.append(f"{Fore.CYAN}{'':>20}⬆️  blocks{Style.RESET_ALL}")

        # Render each blocked issue
        for blocked_issue in blocked_list:
            output_lines.append(
                _render_box_for_issue(blocked_issue, blocked_issue.title)
            )

        output_lines.append("")

    return "\n".join(output_lines)


def _render_box_for_issue(issue: IssueSpec | None, title: str) -> str:
    """Render a single issue in a box format."""
    box_width = 45

    # Truncate title if too long
    display_title = (
        title if len(title) <= box_width - 4 else title[: box_width - 7] + "..."
    )

    lines: list[str] = []
    lines.append(f"{Fore.CYAN}┌{'─' * (box_width - 2)}┐{Style.RESET_ALL}")
    lines.append(
        f"{Fore.CYAN}│{Style.RESET_ALL} {display_title:<{box_width - 4}} {Fore.CYAN}│{Style.RESET_ALL}"
    )

    if issue:
        # Add labels if present
        if issue.labels:
            labels_str = ", ".join(issue.labels)
            if len(labels_str) > box_width - 6:
                labels_str = labels_str[: box_width - 9] + "..."
            lines.append(
                f"{Fore.CYAN}│{Style.RESET_ALL} {Fore.BLUE}[{labels_str}]{Style.RESET_ALL}{' ' * (box_width - len(labels_str) - 7)}{Fore.CYAN}│{Style.RESET_ALL}"
            )

        # Add priority if set
        if issue.priority is not None:
            priority_names = {0: "None", 1: "Low", 2: "Medium", 3: "High", 4: "Urgent"}
            priority_str = (
                f"Priority: {priority_names.get(issue.priority, str(issue.priority))}"
            )
            lines.append(
                f"{Fore.CYAN}│{Style.RESET_ALL} {priority_str:<{box_width - 4}} {Fore.CYAN}│{Style.RESET_ALL}"
            )

        # Add state if present
        if issue.state:
            state_str = f"State: {issue.state}"
            lines.append(
                f"{Fore.CYAN}│{Style.RESET_ALL} {state_str:<{box_width - 4}} {Fore.CYAN}│{Style.RESET_ALL}"
            )
    else:
        # Issue not found in our list
        lines.append(
            f"{Fore.CYAN}│{Style.RESET_ALL} {Fore.YELLOW}(External dependency){Style.RESET_ALL}{' ' * (box_width - 25)}{Fore.CYAN}│{Style.RESET_ALL}"
        )

    lines.append(f"{Fore.CYAN}└{'─' * (box_width - 2)}┘{Style.RESET_ALL}")

    return "\n".join(lines)


def run_list(
    path: Path,
    verbose: bool = False,
    by_project: bool = False,
    by_block: bool = False,
    include_done: bool = False,
) -> int:
    manifest_files = _discover_manifest_files(path)
    if not manifest_files:
        raise RuntimeError(f"No YAML files found in {path}")

    issues: list[IssueSpec] = []
    for manifest_path in manifest_files:
        manifest = load_manifest(manifest_path)
        issues.extend(manifest.issues)

    if not issues:
        print("No issues found.")
        return 0

    # Filter out completed and cancelled tickets unless include_done is True
    if not include_done:
        done_states = {
            "done",
            "completed",
            "complete",
            "closed",
            "resolved",
        }
        cancelled_states = {
            "canceled",
            "cancelled",
            "abandoned",
            "declined",
        }
        excluded_states = done_states | cancelled_states
        issues = [
            issue
            for issue in issues
            if (issue.state or "").lower() not in excluded_states
        ]

    if not issues:
        print(
            "No active issues found. Use --include-done to show completed and cancelled tickets."
        )
        return 0

    if by_block:
        print(_render_by_block(issues))
    elif by_project:
        print(_render_by_project(issues))
    else:
        print(_render_issue_table(issues, verbose=verbose))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="manager",
        description="Manage Linear issues with local YAML files. Push local YAML files to Linear or pull Linear issues to local YAML files.",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # push subcommand
    push_parser = subparsers.add_parser(
        "push",
        help="Push local YAML file(s) to Linear (create/update issues)",
    )
    push_parser.add_argument(
        "path",
        type=Path,
        help="Path to YAML file or directory containing YAML files to push.",
    )
    push_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate manifests without writing to Linear.",
    )

    list_parser = subparsers.add_parser(
        "list",
        help="Display a summary table of issues defined in manifests.",
    )
    list_parser.add_argument(
        "path",
        type=Path,
        nargs="?",
        default=None,
        help="Path to a manifest file or directory containing manifests (defaults to LinearManager/tasks).",
    )
    list_parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Include full descriptions in the output.",
    )
    list_parser.add_argument(
        "--by-project",
        "-p",
        action="store_true",
        help="Group tickets by project instead of showing table view.",
    )
    list_parser.add_argument(
        "--by-block",
        "-b",
        action="store_true",
        help="Show tickets grouped by blocking relationships in a visual tree format.",
    )
    list_parser.add_argument(
        "--include-done",
        "-d",
        action="store_true",
        help="Include completed tickets in the list (by default, completed tickets are hidden).",
    )

    # pull subcommand
    pull_parser = subparsers.add_parser(
        "pull",
        help="Pull issues from Linear to local YAML files (read-only download)",
    )
    pull_parser.add_argument(
        "--team-keys",
        "-t",
        type=str,
        nargs="+",
        required=True,
        help="Team keys to pull issues from (e.g., ENG PROD)",
    )
    pull_parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="Output directory for YAML files (defaults to LinearManager/tasks)",
    )
    pull_parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Maximum number of issues to fetch per team (default: 100)",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    # Handle push subcommand
    if args.command == "push":
        path = args.path
        if path.is_dir():
            # Find all YAML files recursively
            yaml_files = sorted(path.rglob("*.yaml")) + sorted(path.rglob("*.yml"))
            if not yaml_files:
                parser.error(f"No YAML files found in {path}")
                return 1

            print(f"Found {len(yaml_files)} YAML file(s) to push:")
            for yaml_file in yaml_files:
                print(f"  - {yaml_file.relative_to(path)}")
            print()

            failed_files = []
            for yaml_file in yaml_files:
                print(f"==> Pushing {yaml_file.relative_to(path)}")
                config = PushConfig(
                    manifest_path=yaml_file,
                    dry_run=args.dry_run,
                )
                try:
                    run_push(config)
                except Exception as exc:
                    print(f"ERROR: {exc}")
                    failed_files.append(yaml_file)
                print()

            if failed_files:
                print(f"Failed to push {len(failed_files)} file(s):")
                for failed in failed_files:
                    print(f"  - {failed.relative_to(path)}")
                return 1
            return 0
        else:
            # Single file
            config = PushConfig(
                manifest_path=path,
                dry_run=args.dry_run,
            )
            try:
                run_push(config)
                return 0
            except Exception as exc:  # pragma: no cover - top-level handler
                parser.error(str(exc))
                return 1
    elif args.command == "list":
        try:
            path = args.path if args.path is not None else _get_tasks_directory()
            return run_list(
                path,
                verbose=args.verbose,
                by_project=args.by_project,
                by_block=args.by_block,
                include_done=args.include_done,
            )
        except Exception as exc:  # pragma: no cover - top-level handler
            parser.error(str(exc))
            return 1
    elif args.command == "pull":
        try:
            output_dir = (
                args.output if args.output is not None else _get_tasks_directory()
            )
            run_pull(
                team_keys=args.team_keys,
                output_dir=output_dir,
                limit=args.limit,
            )
            return 0
        except Exception as exc:  # pragma: no cover - top-level handler
            parser.error(str(exc))
            return 1
    else:
        # No command provided
        parser.print_help()
        return 1

    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
