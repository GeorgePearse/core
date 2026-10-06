#!/usr/bin/env python3
"""
Test ClickHouse connection and display table schemas.
Run this script to verify your ClickHouse setup is working.
"""

import os
import sys
from pathlib import Path

# Add genesis to path
repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(repo_root))

# Load .env file if it exists
env_file = repo_root / ".env"
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ[key] = value

from genesis.utils.clickhouse_logger import ch_logger


def main():
    print("=" * 60)
    print("Genesis ClickHouse Connection Test")
    print("=" * 60)

    if not ch_logger.enabled:
        print("\n❌ ClickHouse logger is NOT enabled!")
        print("\nPossible reasons:")
        print("  1. CLICKHOUSE_URL not set in environment")
        print("  2. clickhouse-connect not installed (pip install clickhouse-connect)")
        print("  3. Connection failed")
        return 1

    print("\n✅ ClickHouse connection successful!")
    print(f"   Connected to database: {ch_logger.client.database}")

    # List all tables
    print("\n" + "=" * 60)
    print("Tables in database:")
    print("=" * 60)

    try:
        tables = ch_logger.client.query("SHOW TABLES").result_rows
        for table in tables:
            table_name = table[0]
            print(f"\n📊 {table_name}")

            # Get row count
            count = ch_logger.client.query(
                f"SELECT count() FROM {table_name}"
            ).result_rows[0][0]
            print(f"   Rows: {count}")

            # Get schema
            schema = ch_logger.client.query(f"DESCRIBE TABLE {table_name}").result_rows
            print("   Schema:")
            for col in schema:
                col_name, col_type = col[0], col[1]
                print(f"      • {col_name}: {col_type}")

    except Exception as e:
        print(f"\n❌ Error querying tables: {e}")
        return 1

    # Example queries
    print("\n" + "=" * 60)
    print("Example Queries:")
    print("=" * 60)

    queries = [
        (
            "Recent LLM calls",
            "SELECT model, count() as calls, sum(cost) as total_cost FROM llm_logs GROUP BY model ORDER BY calls DESC LIMIT 5",
        ),
        (
            "Recent actions",
            "SELECT action_type, count() as count FROM agent_actions GROUP BY action_type ORDER BY count DESC LIMIT 5",
        ),
        (
            "Evolution runs",
            "SELECT run_id, task_name, status, total_generations FROM evolution_runs ORDER BY start_time DESC LIMIT 5",
        ),
    ]

    for name, query in queries:
        print(f"\n{name}:")
        try:
            results = ch_logger.client.query(query).result_rows
            if results:
                for row in results:
                    print(f"   {row}")
            else:
                print("   (no data yet)")
        except Exception as e:
            print(f"   Error: {e}")

    print("\n" + "=" * 60)
    print("✅ All checks complete!")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
