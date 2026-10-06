#!/usr/bin/env python3
"""Delete Linear issues by ID."""

import os
import sys
from typing import Any

import httpx


def query_linear(query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
    """Execute a GraphQL query against Linear API."""
    api_key = os.environ.get("LINEAR_API_KEY")
    if not api_key:
        raise ValueError("LINEAR_API_KEY environment variable not set")

    headers = {
        "Authorization": api_key,
        "Content-Type": "application/json",
    }

    with httpx.Client() as client:
        response = client.post(
            "https://api.linear.app/graphql",
            json={"query": query, "variables": variables or {}},
            headers=headers,
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()

        if "errors" in data:
            raise ValueError(f"GraphQL errors: {data['errors']}")

        return data["data"]


def delete_issue(issue_id: str) -> dict[str, Any]:
    """Delete a Linear issue by ID."""
    mutation = """
    mutation DeleteIssue($issueId: String!) {
        issueDelete(id: $issueId) {
            success
        }
    }
    """

    variables = {"issueId": issue_id}
    return query_linear(mutation, variables)


def main() -> None:
    """Delete issues provided as command line arguments."""
    if len(sys.argv) < 2:
        print("Usage: python delete_issues.py <issue_id1> <issue_id2> ...")
        sys.exit(1)

    issue_ids = sys.argv[1:]
    print(f"Deleting {len(issue_ids)} issues...\n")

    success_count = 0
    failure_count = 0

    for issue_id in issue_ids:
        try:
            result = delete_issue(issue_id)
            if result["issueDelete"]["success"]:
                print(f"✓ Deleted issue {issue_id}")
                success_count += 1
            else:
                print(f"✗ Failed to delete issue {issue_id}")
                failure_count += 1
        except Exception as e:
            print(f"✗ Error deleting issue {issue_id}: {e}")
            failure_count += 1

    print(f"\n{'=' * 80}")
    print(f"Summary: {success_count} deleted, {failure_count} failed")


if __name__ == "__main__":
    main()
