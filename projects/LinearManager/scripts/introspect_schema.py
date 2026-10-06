#!/usr/bin/env python3
"""Script to introspect Linear GraphQL API and extract IssueCreateInput and IssueUpdateInput field definitions."""

from __future__ import annotations

import json
import os
import sys

import httpx


INTROSPECTION_QUERY = """
query IntrospectionQuery {
  __schema {
    types {
      name
      kind
      inputFields {
        name
        description
        type {
          name
          kind
          ofType {
            name
            kind
            ofType {
              name
              kind
            }
          }
        }
      }
    }
  }
}
"""


def main() -> int:
    """Run introspection query and extract IssueCreateInput and IssueUpdateInput definitions."""
    token = os.environ.get("LINEAR_API_KEY")
    if not token:
        print(
            "ERROR: LINEAR_API_KEY environment variable is required.", file=sys.stderr
        )
        return 1

    print("Querying Linear GraphQL API for schema introspection...")

    try:
        with httpx.Client(timeout=30) as client:
            response = client.post(
                "https://api.linear.app/graphql",
                headers={
                    "Authorization": token,
                    "Content-Type": "application/json",
                },
                json={"query": INTROSPECTION_QUERY},
            )
            response.raise_for_status()
            data = response.json()
    except Exception as exc:
        print(f"ERROR: Failed to query Linear API: {exc}", file=sys.stderr)
        return 1

    if "errors" in data:
        print(f"ERROR: GraphQL errors: {data['errors']}", file=sys.stderr)
        return 1

    types = data.get("data", {}).get("__schema", {}).get("types", [])

    # Find IssueCreateInput and IssueUpdateInput
    create_input = None
    update_input = None

    for type_def in types:
        if type_def.get("name") == "IssueCreateInput":
            create_input = type_def
        elif type_def.get("name") == "IssueUpdateInput":
            update_input = type_def

    if not create_input:
        print("ERROR: IssueCreateInput type not found in schema.", file=sys.stderr)
        return 1

    if not update_input:
        print("ERROR: IssueUpdateInput type not found in schema.", file=sys.stderr)
        return 1

    print("\n" + "=" * 80)
    print("IssueCreateInput")
    print("=" * 80)
    print_input_type(create_input)

    print("\n" + "=" * 80)
    print("IssueUpdateInput")
    print("=" * 80)
    print_input_type(update_input)

    # Save full schema to file for reference
    output_path = "linear_schema_introspection.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print(f"\nFull schema saved to: {output_path}")

    return 0


def print_input_type(type_def: dict) -> None:
    """Print formatted input type definition."""
    fields = type_def.get("inputFields", [])
    if not fields:
        print("  (no fields)")
        return

    required_fields = []
    optional_fields = []

    for field in fields:
        field_name = field.get("name", "")
        field_type = format_type(field.get("type", {}))
        description = field.get("description", "")
        is_required = is_non_null_type(field.get("type", {}))

        field_info = {
            "name": field_name,
            "type": field_type,
            "description": description,
        }

        if is_required:
            required_fields.append(field_info)
        else:
            optional_fields.append(field_info)

    if required_fields:
        print("\nREQUIRED FIELDS:")
        for field in required_fields:
            print(f"  - {field['name']}: {field['type']}")
            if field["description"]:
                print(f"    {field['description']}")
    else:
        print("\nREQUIRED FIELDS: (none)")

    if optional_fields:
        print("\nOPTIONAL FIELDS:")
        for field in optional_fields:
            print(f"  - {field['name']}: {field['type']}")
            if field["description"]:
                print(f"    {field['description']}")


def is_non_null_type(type_info: dict) -> bool:
    """Check if a type is NON_NULL (required)."""
    return type_info.get("kind") == "NON_NULL"


def format_type(type_info: dict | None) -> str:
    """Format a GraphQL type for display."""
    if type_info is None:
        return "Unknown"
    kind = type_info.get("kind", "")
    name = type_info.get("name", "")
    of_type = type_info.get("ofType")

    if kind == "NON_NULL":
        return format_type(of_type) + "!"
    elif kind == "LIST":
        return f"[{format_type(of_type)}]"
    elif name:
        return name
    elif of_type:
        return format_type(of_type)
    else:
        return "Unknown"


if __name__ == "__main__":
    sys.exit(main())
