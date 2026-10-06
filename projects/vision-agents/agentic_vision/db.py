"""Database helpers for inserting VLM experiment results into the vlm_* tables.

All functions use raw psycopg3 SQL with ON CONFLICT upserts, matching the
patterns established in generate_vlm_descriptions.py.
"""

import json
from typing import Any

import psycopg


def get_or_create_vlm_source(conn: psycopg.Connection[Any], source_name: str, config: dict[str, Any]) -> int:
    """Get or create a vlm_source row by name.

    Args:
        conn: psycopg3 connection.
        source_name: Unique name for the VLM source (e.g. "gemini-3-flash-agentic-vision").
        config: JSON-serializable config dict for the source.

    Returns:
        The vlm_source id.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM machine_learning.vlm_sources WHERE source_name = %s",
            (source_name,),
        )
        row = cur.fetchone()
        if row:
            return row[0]

        cur.execute(
            """
            INSERT INTO machine_learning.vlm_sources (source_name, description, config)
            VALUES (%s, %s, %s)
            RETURNING id
            """,
            (source_name, f"Gemini agentic vision ({source_name})", json.dumps(config)),
        )
        row = cur.fetchone()
        conn.commit()
        if row is None:
            raise RuntimeError(f"Failed to insert vlm_source {source_name}")
        return row[0]


def create_vlm_run(
    conn: psycopg.Connection[Any],
    run_name: str,
    vlm_source_id: int,
    config: dict[str, Any],
    script_content: str | None = None,
) -> str:
    """Create a vlm_run record and return its UUID.

    Args:
        conn: psycopg3 connection.
        run_name: Human-readable run name.
        vlm_source_id: FK to vlm_sources.
        config: Run configuration as JSON.
        script_content: Optional Python source that produced this run.

    Returns:
        The vlm_run UUID as a string.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO machine_learning.vlm_runs (run_name, vlm_source_id, config, script_content)
            VALUES (%s, %s, %s, %s)
            RETURNING id
            """,
            (run_name, vlm_source_id, json.dumps(config), script_content),
        )
        row = cur.fetchone()
        conn.commit()
        if row is None:
            raise RuntimeError("Failed to insert vlm_run")
        return str(row[0])


def insert_vlm_image(conn: psycopg.Connection[Any], frame_uri: str) -> str:
    """Insert or get an existing vlm_image by frame_uri (upsert).

    Args:
        conn: psycopg3 connection.
        frame_uri: GCS URI for the image.

    Returns:
        The vlm_image UUID as a string.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO machine_learning.vlm_images (frame_uri)
            VALUES (%s)
            ON CONFLICT (frame_uri) DO UPDATE SET frame_uri = EXCLUDED.frame_uri
            RETURNING id
            """,
            (frame_uri,),
        )
        row = cur.fetchone()
        conn.commit()
        if row is None:
            raise RuntimeError(f"Failed to upsert vlm_image for {frame_uri}")
        return str(row[0])


def link_run_image(conn: psycopg.Connection[Any], vlm_run_id: str, vlm_image_id: str) -> str:
    """Create a vlm_run_images junction record.

    Args:
        conn: psycopg3 connection.
        vlm_run_id: UUID of the vlm_run.
        vlm_image_id: UUID of the vlm_image.

    Returns:
        The vlm_run_image UUID as a string.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO machine_learning.vlm_run_images (vlm_run_id, vlm_image_id)
            VALUES (%s, %s)
            ON CONFLICT (vlm_run_id, vlm_image_id) DO UPDATE SET vlm_run_id = EXCLUDED.vlm_run_id
            RETURNING id
            """,
            (vlm_run_id, vlm_image_id),
        )
        row = cur.fetchone()
        conn.commit()
        if row is None:
            raise RuntimeError("Failed to insert vlm_run_image link")
        return str(row[0])


def insert_raw_response(conn: psycopg.Connection[Any], vlm_run_image_id: str, raw_response: str) -> int:
    """Insert a raw VLM response for a run-image pair.

    Args:
        conn: psycopg3 connection.
        vlm_run_image_id: UUID of the vlm_run_image.
        raw_response: Full raw response text.

    Returns:
        The vlm_raw_response serial id.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO machine_learning.vlm_raw_responses (vlm_run_image_id, raw_response)
            VALUES (%s, %s)
            RETURNING id
            """,
            (vlm_run_image_id, raw_response),
        )
        row = cur.fetchone()
        conn.commit()
        if row is None:
            raise RuntimeError("Failed to insert vlm_raw_response")
        return row[0]


def insert_predictions(
    conn: psycopg.Connection[Any],
    vlm_image_id: str,
    predictions: list[dict[str, Any]],
) -> list[int]:
    """Insert bounding box predictions for an image.

    Each prediction dict should have keys: x1, y1, x2, y2 (normalized 0-1),
    and optionally: confidence, vlm_label, description, extra_data.

    Args:
        conn: psycopg3 connection.
        vlm_image_id: UUID of the vlm_image.
        predictions: List of prediction dicts.

    Returns:
        List of inserted prediction serial ids.
    """
    ids: list[int] = []
    with conn.cursor() as cur:
        for pred in predictions:
            extra_data = pred.get("extra_data")
            cur.execute(
                """
                INSERT INTO machine_learning.vlm_predictions
                    (vlm_image_id, x1, y1, x2, y2, confidence, vlm_label, description, extra_data)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    vlm_image_id,
                    pred["x1"],
                    pred["y1"],
                    pred["x2"],
                    pred["y2"],
                    pred.get("confidence"),
                    pred.get("vlm_label"),
                    pred.get("description"),
                    json.dumps(extra_data) if extra_data else None,
                ),
            )
            row = cur.fetchone()
            if row:
                ids.append(row[0])
    conn.commit()
    return ids


def insert_image_description(
    conn: psycopg.Connection[Any],
    vlm_image_id: str,
    vlm_source_id: int,
    description_data: dict[str, Any],
) -> int:
    """Insert or update an image-level description.

    Args:
        conn: psycopg3 connection.
        vlm_image_id: UUID of the vlm_image.
        vlm_source_id: FK to vlm_sources.
        description_data: Dict with optional keys: dump_description, pile_contents,
            is_dump_visible, dump_box_coords.

    Returns:
        The vlm_image_description serial id.
    """
    dump_box_coords = description_data.get("dump_box_coords")
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO machine_learning.vlm_image_descriptions
                (vlm_image_id, vlm_source_id, dump_description, pile_contents, is_dump_visible, dump_box_coords)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (vlm_image_id, vlm_source_id) DO UPDATE
            SET dump_description = EXCLUDED.dump_description,
                pile_contents = EXCLUDED.pile_contents,
                is_dump_visible = EXCLUDED.is_dump_visible,
                dump_box_coords = EXCLUDED.dump_box_coords
            RETURNING id
            """,
            (
                vlm_image_id,
                vlm_source_id,
                description_data.get("dump_description"),
                description_data.get("pile_contents"),
                description_data.get("is_dump_visible", False),
                json.dumps(dump_box_coords) if dump_box_coords else None,
            ),
        )
        row = cur.fetchone()
        conn.commit()
        if row is None:
            raise RuntimeError("Failed to insert vlm_image_description")
        return row[0]
