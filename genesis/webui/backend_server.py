#!/usr/bin/env python3
"""
Genesis WebUI Backend Server - ClickHouse Edition

Provides REST API endpoints for the Genesis WebUI frontend.
Connects to ClickHouse to serve evolution experiment data.
"""

import os
import re
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import clickhouse_connect
import uvicorn

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Initialize FastAPI
app = FastAPI(
    title="Genesis WebUI API",
    description="Backend API for Genesis Evolution Visualization",
    version="1.0.0",
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ClickHouse client (will be initialized on startup)
ch_client = None
RUN_ID_RE = re.compile(r"^[A-Za-z0-9._:-]+$")
PROGRAM_ID_RE = re.compile(r"^[A-Za-z0-9-]+$")
TASK_RE = re.compile(r"^[A-Za-z0-9_.:-]+$")
DB_PATH_RE = re.compile(r"^[A-Za-z0-9_./:-]+$")


def _escape_sql_literal(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "''")


def _validate_or_400(value: str, pattern: re.Pattern[str], field_name: str) -> str:
    if not pattern.fullmatch(value):
        raise HTTPException(status_code=400, detail=f"Invalid {field_name}")
    return value


def parse_clickhouse_url(url: str) -> Dict[str, Any]:
    """Parse ClickHouse URL into connection parameters."""
    match = re.match(r"https?://([^:]+):([^@]+)@([^:]+):(\d+)", url)
    if match:
        return {
            "host": match.group(3),
            "port": int(match.group(4)),
            "username": match.group(1),
            "password": match.group(2),
            "secure": url.startswith("https"),
        }
    raise ValueError(f"Invalid ClickHouse URL format: {url}")


def get_clickhouse_client():
    """Get or create ClickHouse client."""
    global ch_client
    if ch_client is None:
        url = os.getenv("CLICKHOUSE_URL")
        if url:
            params = parse_clickhouse_url(url)
            ch_client = clickhouse_connect.get_client(
                host=params["host"],
                port=params["port"],
                username=params["username"],
                password=params["password"],
                secure=params["secure"],
                connect_timeout=30,
                send_receive_timeout=60,
            )
            logger.info(f"Connected to ClickHouse at {params['host']}:{params['port']}")
        else:
            # Fallback to individual env vars
            ch_client = clickhouse_connect.get_client(
                host=os.getenv("CLICKHOUSE_HOST", "localhost"),
                port=int(os.getenv("CLICKHOUSE_PORT", 8123)),
                username=os.getenv("CLICKHOUSE_USER", "default"),
                password=os.getenv("CLICKHOUSE_PASSWORD", ""),
                database=os.getenv("CLICKHOUSE_DB", "default"),
                connect_timeout=30,
                send_receive_timeout=60,
            )
            logger.info("Connected to ClickHouse using individual env vars")
    return ch_client


@app.on_event("startup")
async def startup_event():
    """Initialize ClickHouse connection on startup."""
    try:
        client = get_clickhouse_client()
        result = client.command("SELECT 1")
        logger.info(f"✅ ClickHouse connection verified: {result}")
    except Exception as e:
        logger.error(f"❌ Failed to connect to ClickHouse: {e}")


@app.get("/")
async def root():
    """Health check endpoint."""
    return {
        "service": "Genesis WebUI API",
        "status": "running",
        "clickhouse": "connected" if ch_client else "disconnected",
    }


@app.get("/api/experiments")
async def list_experiments(
    limit: int = Query(50, ge=1, le=500), task: Optional[str] = None
):
    """
    List all evolution experiments stored in ClickHouse.

    Returns experiment metadata grouped by run.
    """
    try:
        client = get_clickhouse_client()

        # Build query
        where_clause = ""
        if task:
            task = _validate_or_400(task, TASK_RE, "task")
            escaped_task = _escape_sql_literal(task)
            where_clause = (
                f"WHERE JSONExtractString(metadata, 'original_run_id') LIKE '%{escaped_task}%'"
            )

        query = f"""
        SELECT 
            JSONExtractString(metadata, 'original_run_id') as run_id,
            count() as total_programs,
            max(generation) as max_generation,
            max(combined_score) as best_score,
            avg(combined_score) as avg_score,
            max(timestamp) as last_updated,
            any(language) as language,
            any(JSONExtractString(metadata, 'migration_source')) as source_path
        FROM programs
        {where_clause}
        GROUP BY run_id
        ORDER BY last_updated DESC
        LIMIT {limit}
        """

        result = client.query(query)

        experiments = []
        for row in result.result_rows:
            run_id, total, max_gen, best, avg, updated, lang, source_path = row

            # Parse task name from run_id
            task_name = run_id.split("_")[0] if run_id else "unknown"

            experiments.append(
                {
                    "run_id": run_id,
                    "task_name": task_name,
                    "source_path": source_path,
                    "total_programs": total,
                    "max_generation": max_gen,
                    "best_score": float(best) if best else 0.0,
                    "avg_score": float(avg) if avg else 0.0,
                    "last_updated": updated,
                    "language": lang,
                }
            )

        return {"experiments": experiments, "total": len(experiments)}

    except Exception as e:
        logger.error(f"Error listing experiments: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/experiments/{run_id}/programs")
async def get_programs(
    run_id: str,
    limit: int = Query(100, ge=1, le=1000),
    generation: Optional[int] = None,
):
    """
    Get all programs for a specific experiment run.
    """
    try:
        run_id = _validate_or_400(run_id, RUN_ID_RE, "run_id")
        client = get_clickhouse_client()
        escaped_run_id = _escape_sql_literal(run_id)

        where_clauses = [
            f"JSONExtractString(metadata, 'original_run_id') = '{escaped_run_id}'"
        ]
        if generation is not None:
            where_clauses.append(f"generation = {generation}")

        where_clause = " AND ".join(where_clauses)

        query = f"""
        SELECT 
            id,
            language,
            parent_id,
            generation,
            timestamp,
            combined_score,
            public_metrics,
            island_idx,
            complexity,
            children_count
        FROM programs
        WHERE {where_clause}
        ORDER BY generation, timestamp
        LIMIT {limit}
        """

        result = client.query(query)

        programs = []
        for row in result.result_rows:
            (
                prog_id,
                lang,
                parent,
                gen,
                ts,
                score,
                metrics_str,
                island,
                complexity,
                children,
            ) = row

            # Parse metrics JSON
            try:
                metrics = json.loads(metrics_str) if metrics_str else {}
            except:
                metrics = {}

            programs.append(
                {
                    "id": prog_id,
                    "language": lang,
                    "parent_id": parent,
                    "generation": gen,
                    "timestamp": ts,
                    "combined_score": float(score) if score else 0.0,
                    "public_metrics": metrics,
                    "island_idx": island,
                    "complexity": float(complexity) if complexity else 0.0,
                    "children_count": children,
                }
            )

        return {"run_id": run_id, "programs": programs, "total": len(programs)}

    except Exception as e:
        logger.error(f"Error fetching programs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/experiments/{run_id}/programs/{program_id}")
async def get_program_detail(run_id: str, program_id: str):
    """
    Get detailed information for a specific program including code.
    """
    try:
        run_id = _validate_or_400(run_id, RUN_ID_RE, "run_id")
        program_id = _validate_or_400(program_id, PROGRAM_ID_RE, "program_id")
        client = get_clickhouse_client()
        escaped_run_id = _escape_sql_literal(run_id)
        escaped_program_id = _escape_sql_literal(program_id)

        query = f"""
        SELECT 
            id,
            code,
            language,
            parent_id,
            archive_inspiration_ids,
            top_k_inspiration_ids,
            generation,
            timestamp,
            code_diff,
            combined_score,
            public_metrics,
            private_metrics,
            text_feedback,
            complexity,
            embedding_cluster_id,
            correct,
            children_count,
            metadata,
            island_idx,
            migration_history,
            in_archive
        FROM programs
        WHERE id = '{escaped_program_id}' 
        AND JSONExtractString(metadata, 'original_run_id') = '{escaped_run_id}'
        LIMIT 1
        """

        result = client.query(query)

        if not result.result_rows:
            raise HTTPException(status_code=404, detail="Program not found")

        row = result.result_rows[0]

        # Parse JSON fields
        def safe_json_parse(s):
            try:
                return json.loads(s) if s else {}
            except:
                return {}

        program = {
            "id": row[0],
            "code": row[1],
            "language": row[2],
            "parent_id": row[3],
            "archive_inspiration_ids": safe_json_parse(row[4]),
            "top_k_inspiration_ids": safe_json_parse(row[5]),
            "generation": row[6],
            "timestamp": row[7],
            "code_diff": row[8],
            "combined_score": float(row[9]) if row[9] else 0.0,
            "public_metrics": safe_json_parse(row[10]),
            "private_metrics": safe_json_parse(row[11]),
            "text_feedback": row[12],
            "complexity": float(row[13]) if row[13] else 0.0,
            "embedding_cluster_id": row[14],
            "correct": bool(row[15]),
            "children_count": row[16],
            "metadata": safe_json_parse(row[17]),
            "island_idx": row[18],
            "migration_history": safe_json_parse(row[19]),
            "in_archive": bool(row[20]),
        }

        return program

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching program detail: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/experiments/{run_id}/stats")
async def get_experiment_stats(run_id: str):
    """
    Get statistical summary for an experiment.
    """
    try:
        run_id = _validate_or_400(run_id, RUN_ID_RE, "run_id")
        client = get_clickhouse_client()
        escaped_run_id = _escape_sql_literal(run_id)

        query = f"""
        SELECT 
            count() as total_programs,
            count(DISTINCT generation) as total_generations,
            count(DISTINCT island_idx) as num_islands,
            max(combined_score) as best_score,
            avg(combined_score) as avg_score,
            min(combined_score) as worst_score,
            max(generation) as max_generation,
            sum(CASE WHEN in_archive = 1 THEN 1 ELSE 0 END) as archive_count
        FROM programs
        WHERE JSONExtractString(metadata, 'original_run_id') = '{escaped_run_id}'
        """

        result = client.query(query)

        if not result.result_rows:
            raise HTTPException(status_code=404, detail="Experiment not found")

        row = result.result_rows[0]

        stats = {
            "total_programs": row[0],
            "total_generations": row[1],
            "num_islands": row[2],
            "best_score": float(row[3]) if row[3] else 0.0,
            "avg_score": float(row[4]) if row[4] else 0.0,
            "worst_score": float(row[5]) if row[5] else 0.0,
            "max_generation": row[6],
            "archive_count": row[7],
        }

        # Get generation-by-generation stats
        gen_query = f"""
        SELECT 
            generation,
            count() as count,
            max(combined_score) as best,
            avg(combined_score) as avg
        FROM programs
        WHERE JSONExtractString(metadata, 'original_run_id') = '{escaped_run_id}'
        GROUP BY generation
        ORDER BY generation
        """

        gen_result = client.query(gen_query)

        generations = []
        for gen_row in gen_result.result_rows:
            generations.append(
                {
                    "generation": gen_row[0],
                    "count": gen_row[1],
                    "best_score": float(gen_row[2]) if gen_row[2] else 0.0,
                    "avg_score": float(gen_row[3]) if gen_row[3] else 0.0,
                }
            )

        stats["generations"] = generations

        return stats

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching experiment stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/experiments/{run_id}/lineage")
async def get_lineage(run_id: str):
    """
    Get parent-child lineage graph for visualization.
    """
    try:
        run_id = _validate_or_400(run_id, RUN_ID_RE, "run_id")
        client = get_clickhouse_client()
        escaped_run_id = _escape_sql_literal(run_id)

        query = f"""
        SELECT 
            id,
            parent_id,
            generation,
            combined_score,
            island_idx
        FROM programs
        WHERE JSONExtractString(metadata, 'original_run_id') = '{escaped_run_id}'
        AND parent_id != ''
        ORDER BY generation, timestamp
        """

        result = client.query(query)

        nodes = []
        edges = []

        for row in result.result_rows:
            prog_id, parent_id, gen, score, island = row

            nodes.append(
                {
                    "id": prog_id,
                    "generation": gen,
                    "score": float(score) if score else 0.0,
                    "island": island,
                }
            )

            if parent_id:
                edges.append({"source": parent_id, "target": prog_id})

        return {
            "nodes": nodes,
            "edges": edges,
            "total_nodes": len(nodes),
            "total_edges": len(edges),
        }

    except Exception as e:
        logger.error(f"Error fetching lineage: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/list_databases")
async def list_databases_legacy():
    """
    Legacy endpoint for frontend compatibility.
    Returns list of available experiment runs from ClickHouse.
    """
    try:
        client = get_clickhouse_client()

        query = """
        SELECT 
            JSONExtractString(metadata, 'original_run_id') as run_id,
            JSONExtractString(metadata, 'migration_source') as source_path,
            count() as total,
            sum(CASE WHEN correct = 1 THEN 1 ELSE 0 END) as working
        FROM programs
        WHERE JSONExtractString(metadata, 'original_run_id') != ''
        GROUP BY run_id, source_path
        ORDER BY max(timestamp) DESC
        """

        result = client.query(query)

        databases = []
        for row in result.result_rows:
            run_id, source_path, total, working = row
            if not run_id:
                continue

            # Normalize path for frontend parsing
            # Frontend expects: .../task/result/filename
            path = source_path or run_id
            if path and "/" in path and not path.endswith(".sqlite"):
                path = f"{path.rstrip('/')}/clickhouse_dummy"

            databases.append(
                {
                    "path": path,
                    "name": run_id,
                    "actual_path": source_path or run_id,
                    "sort_key": run_id.split("_")[-1] if "_" in run_id else "0",
                    "stats": {"total": total, "working": working},
                }
            )

        return databases

    except Exception as e:
        logger.error(f"Error listing databases: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/get_programs")
async def get_programs_legacy(db_path: str = Query(..., alias="db_path")):
    """
    Legacy endpoint for frontend compatibility.
    Get all programs for a specific run from ClickHouse.
    """
    try:
        db_path = _validate_or_400(db_path, DB_PATH_RE, "db_path")
        client = get_clickhouse_client()

        # Handle frontend path normalization
        search_path = db_path
        if search_path.endswith("/clickhouse_dummy"):
            search_path = search_path.replace("/clickhouse_dummy", "")
        escaped_search_path = _escape_sql_literal(search_path)

        query = f"""
        SELECT 
            id,
            code,
            language,
            parent_id,
            archive_inspiration_ids,
            top_k_inspiration_ids,
            generation,
            timestamp,
            code_diff,
            combined_score,
            public_metrics,
            private_metrics,
            text_feedback,
            complexity,
            embedding_cluster_id,
            correct,
            children_count,
            metadata,
            island_idx,
            embedding_pca_2d,
            embedding_pca_3d,
            embedding
        FROM programs
        WHERE (JSONExtractString(metadata, 'original_run_id') = '{escaped_search_path}'
           OR JSONExtractString(metadata, 'migration_source') = '{escaped_search_path}')
        ORDER BY generation, timestamp
        """

        result = client.query(query)

        programs = []
        for row in result.result_rows:
            # Parse JSON fields
            def safe_json_parse(s):
                try:
                    return json.loads(s) if s else []
                except:
                    return []

            def safe_json_parse_dict(s):
                try:
                    return json.loads(s) if s else {}
                except:
                    return {}

            program = {
                "id": row[0],
                "code": row[1],
                "language": row[2],
                "parent_id": row[3] or None,
                "archive_inspiration_ids": safe_json_parse(row[4]),
                "top_k_inspiration_ids": safe_json_parse(row[5]),
                "generation": row[6],
                "timestamp": row[7],
                "code_diff": row[8] or "",
                "combined_score": float(row[9]) if row[9] is not None else None,
                "public_metrics": safe_json_parse_dict(row[10]),
                "private_metrics": safe_json_parse_dict(row[11]),
                "text_feedback": row[12] or "",
                "complexity": float(row[13]) if row[13] else 0.0,
                "embedding_cluster_id": row[14] or 0,
                "correct": bool(row[15]),
                "children_count": row[16] or 0,
                "metadata": safe_json_parse_dict(row[17]),
                "island_idx": row[18] or 0,
                "embedding_pca_2d": safe_json_parse(row[19]),
                "embedding_pca_3d": safe_json_parse(row[20]),
                "embedding": row[21] or [],
            }

            programs.append(program)

        return programs

    except Exception as e:
        logger.error(f"Error fetching programs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/database/info")
async def database_info():
    """
    Get ClickHouse database information.
    """
    try:
        client = get_clickhouse_client()

        # Get table counts
        programs_count = client.command("SELECT count() FROM programs")
        archive_count = client.command("SELECT count() FROM archive")
        metadata_count = client.command("SELECT count() FROM metadata_store")

        # Get database size
        size_query = """
        SELECT 
            formatReadableSize(sum(bytes)) as total_size
        FROM system.parts
        WHERE database = currentDatabase()
        AND active = 1
        """
        size_result = client.query(size_query)
        total_size = size_result.result_rows[0][0] if size_result.result_rows else "0 B"

        return {
            "tables": {
                "programs": programs_count,
                "archive": archive_count,
                "metadata_store": metadata_count,
            },
            "total_size": total_size,
            "database": "ClickHouse",
            "status": "connected",
        }

    except Exception as e:
        logger.error(f"Error fetching database info: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def main():
    """Run the server."""
    port = int(os.getenv("GENESIS_WEBUI_PORT", 8000))
    logger.info(f"Starting Genesis WebUI Backend on port {port}")

    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    main()
