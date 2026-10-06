#!/usr/bin/env python3
"""
Migrate all SQLite evolution databases to ClickHouse.

This script:
1. Finds all evolution_db.sqlite files in the results directory
2. Extracts data from programs, archive, and metadata_store tables
3. Uploads the data to ClickHouse with proper run tracking
"""

import os
import sys
import json
import sqlite3
import logging
from pathlib import Path
from typing import List, Dict, Any
import clickhouse_connect
from dotenv import load_dotenv
from datetime import datetime

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()


def parse_clickhouse_url(url: str) -> Dict[str, Any]:
    """Parse ClickHouse URL into connection parameters."""
    # Format: https://user:password@host:port
    import re

    match = re.match(r"https?://([^:]+):([^@]+)@([^:]+):(\d+)", url)
    if match:
        return {
            "host": match.group(3),
            "port": int(match.group(4)),
            "username": match.group(1),
            "password": match.group(2),
            "secure": True,
        }
    raise ValueError(f"Invalid ClickHouse URL format: {url}")


def get_clickhouse_client():
    """Connect to ClickHouse."""
    url = os.getenv("CLICKHOUSE_URL")
    if not url:
        raise ValueError("CLICKHOUSE_URL not set in environment")

    params = parse_clickhouse_url(url)
    logger.info(f"Connecting to ClickHouse at {params['host']}:{params['port']}")

    client = clickhouse_connect.get_client(
        host=params["host"],
        port=params["port"],
        username=params["username"],
        password=params["password"],
        secure=params["secure"],
    )
    return client


def create_tables(client):
    """Create ClickHouse tables if they don't exist."""
    logger.info("Creating ClickHouse tables if they don't exist...")

    # Programs table
    client.command("""
        CREATE TABLE IF NOT EXISTS programs (
            id String,
            code String,
            language String,
            parent_id String,
            archive_inspiration_ids String, -- JSON
            top_k_inspiration_ids String, -- JSON
            generation Int32,
            timestamp Float64,
            code_diff String,
            combined_score Float64,
            public_metrics String, -- JSON
            private_metrics String, -- JSON
            text_feedback String,
            complexity Float64,
            embedding Array(Float32),
            embedding_pca_2d String, -- JSON
            embedding_pca_3d String, -- JSON
            embedding_cluster_id Int32,
            correct UInt8,
            children_count Int32,
            metadata String, -- JSON
            island_idx Int32,
            migration_history String, -- JSON
            in_archive UInt8 DEFAULT 0
        ) ENGINE = ReplacingMergeTree(timestamp)
        ORDER BY id
    """)

    # Archive table
    client.command("""
        CREATE TABLE IF NOT EXISTS archive (
            program_id String,
            timestamp DateTime64(3) DEFAULT now()
        ) ENGINE = ReplacingMergeTree()
        ORDER BY program_id
    """)

    # Metadata store
    client.command("""
        CREATE TABLE IF NOT EXISTS metadata_store (
            key String,
            value String,
            timestamp DateTime64(3) DEFAULT now()
        ) ENGINE = ReplacingMergeTree(timestamp)
        ORDER BY key
    """)

    logger.info("✅ Tables created/verified")


def find_sqlite_databases(base_path: str = "results") -> List[Path]:
    """Find all SQLite database files."""
    base = Path(base_path)
    if not base.exists():
        logger.warning(f"Results directory not found: {base_path}")
        return []

    databases = list(base.rglob("evolution_db.sqlite"))
    logger.info(f"Found {len(databases)} SQLite databases")
    return databases


def extract_run_metadata(db_path: Path) -> Dict[str, Any]:
    """Extract run metadata from database path and contents."""
    parts = db_path.parts

    # Extract task name and timestamp from path
    # Format: results/genesis_{task}/{timestamp}_{variant}/evolution_db.sqlite
    task_name = "unknown"
    timestamp_str = "unknown"
    variant = "unknown"

    if len(parts) >= 3:
        task_dir = parts[-3]  # e.g., "genesis_circle_packing"
        if task_dir.startswith("genesis_"):
            task_name = task_dir.replace("genesis_", "")

        run_dir = parts[-2]  # e.g., "2025.11.24191253_example"
        if "_" in run_dir:
            timestamp_str, variant = run_dir.rsplit("_", 1)

    return {
        "task_name": task_name,
        "timestamp": timestamp_str,
        "variant": variant,
        "db_path": str(db_path),
        "run_id": f"{task_name}_{timestamp_str}_{variant}",
    }


def migrate_database(sqlite_path: Path, clickhouse_client) -> bool:
    """Migrate a single SQLite database to ClickHouse."""
    try:
        logger.info(f"\nMigrating: {sqlite_path}")

        # Extract metadata
        metadata = extract_run_metadata(sqlite_path)
        run_id = metadata["run_id"]

        # Check if already migrated
        existing = clickhouse_client.command(
            f"SELECT count() FROM programs WHERE metadata LIKE '%{run_id}%'"
        )
        if existing > 0:
            logger.info(
                f"  ⚠️  Run {run_id} already has {existing} records in ClickHouse, skipping..."
            )
            return False

        # Connect to SQLite
        conn = sqlite3.connect(str(sqlite_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Get programs
        cursor.execute("SELECT * FROM programs")
        programs = [dict(row) for row in cursor.fetchall()]
        logger.info(f"  Found {len(programs)} programs")

        if not programs:
            logger.info(f"  Skipping empty database")
            conn.close()
            return False

        # Prepare data for ClickHouse insertion
        rows = []
        for prog in programs:
            # Parse JSON fields
            try:
                archive_insp = (
                    json.loads(prog["archive_inspiration_ids"])
                    if prog["archive_inspiration_ids"]
                    else []
                )
                top_k_insp = (
                    json.loads(prog["top_k_inspiration_ids"])
                    if prog["top_k_inspiration_ids"]
                    else []
                )
                public_metrics = (
                    json.loads(prog["public_metrics"]) if prog["public_metrics"] else {}
                )
                private_metrics = (
                    json.loads(prog["private_metrics"])
                    if prog["private_metrics"]
                    else {}
                )
                embedding = json.loads(prog["embedding"]) if prog["embedding"] else []
                embedding_pca_2d = (
                    json.loads(prog["embedding_pca_2d"])
                    if prog["embedding_pca_2d"]
                    else []
                )
                embedding_pca_3d = (
                    json.loads(prog["embedding_pca_3d"])
                    if prog["embedding_pca_3d"]
                    else []
                )
                metadata_dict = json.loads(prog["metadata"]) if prog["metadata"] else {}
                migration_history = (
                    json.loads(prog["migration_history"])
                    if prog["migration_history"]
                    else []
                )
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning(f"  ⚠️  JSON parse error for program {prog['id']}: {e}")
                archive_insp = []
                top_k_insp = []
                public_metrics = {}
                private_metrics = {}
                embedding = []
                embedding_pca_2d = []
                embedding_pca_3d = []
                metadata_dict = {}
                migration_history = []

            # Add migration metadata
            metadata_dict["migration_source"] = str(sqlite_path)
            metadata_dict["migration_date"] = datetime.now().isoformat()
            metadata_dict["original_run_id"] = run_id

            row = [
                prog["id"] or "",
                prog["code"] or "",
                prog["language"] or "python",
                prog["parent_id"] or "",
                json.dumps(archive_insp),
                json.dumps(top_k_insp),
                int(prog["generation"] or 0),
                float(prog["timestamp"] or 0.0),
                prog["code_diff"] or "",
                float(prog["combined_score"] or 0.0),
                json.dumps(public_metrics),
                json.dumps(private_metrics),
                prog["text_feedback"] or "",
                float(prog["complexity"] or 0.0),
                embedding,  # Array for ClickHouse
                json.dumps(embedding_pca_2d),
                json.dumps(embedding_pca_3d),
                int(prog["embedding_cluster_id"] or 0),
                int(prog["correct"] or 0),
                int(prog["children_count"] or 0),
                json.dumps(metadata_dict),
                int(prog["island_idx"] or 0),
                json.dumps(migration_history),
                0,  # in_archive
            ]
            rows.append(row)

        # Insert into ClickHouse
        logger.info(f"  Inserting {len(rows)} programs into ClickHouse...")
        clickhouse_client.insert(
            "programs",
            rows,
            column_names=[
                "id",
                "code",
                "language",
                "parent_id",
                "archive_inspiration_ids",
                "top_k_inspiration_ids",
                "generation",
                "timestamp",
                "code_diff",
                "combined_score",
                "public_metrics",
                "private_metrics",
                "text_feedback",
                "complexity",
                "embedding",
                "embedding_pca_2d",
                "embedding_pca_3d",
                "embedding_cluster_id",
                "correct",
                "children_count",
                "metadata",
                "island_idx",
                "migration_history",
                "in_archive",
            ],
        )

        # Migrate archive table
        cursor.execute("SELECT * FROM archive")
        archive_rows = [dict(row) for row in cursor.fetchall()]
        if archive_rows:
            logger.info(f"  Migrating {len(archive_rows)} archive entries...")
            archive_data = [[row["program_id"]] for row in archive_rows]
            clickhouse_client.insert(
                "archive", archive_data, column_names=["program_id"]
            )

        # Migrate metadata_store
        cursor.execute("SELECT * FROM metadata_store")
        metadata_rows = [dict(row) for row in cursor.fetchall()]
        if metadata_rows:
            # Filter out rows with None values
            meta_data = [
                [
                    f"{run_id}_{row['key']}",
                    str(row["value"]) if row["value"] is not None else "",
                ]
                for row in metadata_rows
                if row["key"] is not None
            ]
            if meta_data:
                logger.info(f"  Migrating {len(meta_data)} metadata entries...")
                clickhouse_client.insert(
                    "metadata_store", meta_data, column_names=["key", "value"]
                )

        conn.close()
        logger.info(f"  ✅ Migration successful!")
        return True

    except Exception as e:
        logger.error(f"  ❌ Migration failed: {e}", exc_info=True)
        return False


def main():
    """Main migration process."""
    logger.info("=" * 80)
    logger.info("SQLite to ClickHouse Migration Tool")
    logger.info("=" * 80)

    # Get ClickHouse client
    try:
        ch_client = get_clickhouse_client()
        logger.info("✅ Connected to ClickHouse")

        # Create tables if they don't exist
        create_tables(ch_client)
    except Exception as e:
        logger.error(f"❌ Failed to connect to ClickHouse: {e}")
        return 1

    # Find all SQLite databases
    databases = find_sqlite_databases()
    if not databases:
        logger.warning("No SQLite databases found to migrate")
        return 0

    # Migrate each database
    success_count = 0
    skip_count = 0
    fail_count = 0

    for db_path in databases:
        result = migrate_database(db_path, ch_client)
        if result is True:
            success_count += 1
        elif result is False:
            skip_count += 1
        else:
            fail_count += 1

    # Summary
    logger.info("\n" + "=" * 80)
    logger.info("Migration Summary")
    logger.info("=" * 80)
    logger.info(f"Total databases found: {len(databases)}")
    logger.info(f"✅ Successfully migrated: {success_count}")
    logger.info(f"⚠️  Skipped (already migrated): {skip_count}")
    logger.info(f"❌ Failed: {fail_count}")
    logger.info("=" * 80)

    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
