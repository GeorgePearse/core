#!/usr/bin/env python3
"""List issues created in the last N minutes."""

import os
import sys
from datetime import datetime, timedelta, timezone
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


def get_current_user() -> dict[str, Any]:
    """Get the current authenticated user."""
    query = """
    query {
        viewer {
            id
            name
            email
        }
    }
    """
    data = query_linear(query)
    return data["viewer"]


def list_recent_issues(minutes: int = 5) -> list[dict[str, Any]]:
    """List issues created by the current user in the last N minutes."""
    user = get_current_user()
    print(f"Authenticated as: {user['name']} ({user['email']})")
    print(f"User ID: {user['id']}\n")

    # Calculate the cutoff time
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)

    # Query for all issues created by the user, sorted by creation date
    query = """
    query($first: Int!, $after: String) {
        issues(
            first: $first
            after: $after
            orderBy: createdAt
            filter: {
                creator: { id: { eq: "37b5944c-0d9a-4682-8f12-f31d8d105b2a" } }
            }
        ) {
            nodes {
                id
                identifier
                title
                createdAt
                creator {
                    id
                    name
                    email
                }
                state {
                    name
                }
                team {
                    key
                }
                assignee {
                    name
                    email
                }
                priority
                labels {
                    nodes {
                        name
                    }
                }
            }
            pageInfo {
                hasNextPage
                endCursor
            }
        }
    }
    """

    # Fetch the most recent issues
    variables = {
        "first": 100,
        "after": None,
    }

    data = query_linear(query, variables)
    all_issues = data["issues"]["nodes"]

    # Filter to only issues created after the cutoff
    issues = [
        issue
        for issue in all_issues
        if datetime.fromisoformat(issue["createdAt"].replace("Z", "+00:00")) > cutoff
    ]

    print(f"Found {len(issues)} issues created in the last {minutes} minutes:\n")

    for issue in issues:
        created_at = datetime.fromisoformat(issue["createdAt"].replace("Z", "+00:00"))
        labels = [label["name"] for label in issue["labels"]["nodes"]]
        assignee = issue.get("assignee")
        assignee_str = (
            f"{assignee['name']} ({assignee['email']})" if assignee else "Unassigned"
        )

        print(f"ID: {issue['id']}")
        print(f"Identifier: {issue['identifier']}")
        print(f"Title: {issue['title']}")
        print(f"Team: {issue['team']['key']}")
        print(f"State: {issue['state']['name']}")
        print(f"Priority: {issue['priority']}")
        print(f"Assignee: {assignee_str}")
        print(f"Labels: {', '.join(labels) if labels else 'None'}")
        print(f"Created: {created_at.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        print("-" * 80)
        print()

    return issues


if __name__ == "__main__":
    minutes = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    issues = list_recent_issues(minutes)

    if issues:
        print(f"\nTotal: {len(issues)} issues")
        print("\nTo delete these issues, run:")
        print(f"  python delete_issues.py {' '.join(issue['id'] for issue in issues)}")
    else:
        print("No issues found in the specified time range.")
