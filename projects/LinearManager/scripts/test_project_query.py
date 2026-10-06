#!/usr/bin/env python3
"""Test query to explore project field in Linear issues."""

import os
import httpx
import json

# Test query to get issue with project field
TEST_QUERY = """
query TestProjectField($teamKey: String!) {
  teams(filter: { key: { eq: $teamKey }}) {
    nodes {
      issues(first: 10) {
        nodes {
          id
          identifier
          title
          project {
            id
            name
            description
          }
        }
      }
    }
  }
}
"""


def main():
    token = os.environ.get("LINEAR_API_KEY")
    if not token:
        print("ERROR: LINEAR_API_KEY environment variable is required.")
        return 1

    # Try with a known team key (we'll use "ENG" as it was in examples)
    team_key = "ENG"

    with httpx.Client(timeout=30) as client:
        response = client.post(
            "https://api.linear.app/graphql",
            headers={
                "Authorization": token,
                "Content-Type": "application/json",
            },
            json={"query": TEST_QUERY, "variables": {"teamKey": team_key}},
        )

        result = response.json()
        print(json.dumps(result, indent=2))

    return 0


if __name__ == "__main__":
    exit(main())
