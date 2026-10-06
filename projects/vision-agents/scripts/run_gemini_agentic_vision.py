"""Run Gemini 3 Flash Agentic Vision against images and store results in vlm_* tables.

Usage:
    uv run python scripts/run_gemini_agentic_vision.py \
        --dataset-name construction_demolition --limit 5

    (run from the agentic_vision package directory)

Requirements:
    - GEMINI_API_KEY environment variable set
    - PG_DATABASE_URL environment variable set
    - GCS credentials configured (GOOGLE_APPLICATION_CREDENTIALS or MODEL_TRAINING_SA_KEY)

This script:
1. Fetches image frame_uris from machine_learning.images by dataset name
2. Creates a vlm_run record with config and script content
3. For each image: downloads from GCS, calls Gemini agentic vision, stores results
4. Results go into: vlm_images, vlm_run_images, vlm_raw_responses, vlm_image_descriptions
5. Runs locally (no Modal/GPU needed - Gemini is API-based)
"""

import argparse
import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psycopg
from google.cloud import storage

from agentic_vision.db import (
    create_vlm_run,
    get_or_create_vlm_source,
    insert_image_description,
    insert_raw_response,
    insert_vlm_image,
    link_run_image,
)
from agentic_vision.gemini_agentic_vision import GeminiAgenticVisionClient


def get_db_connection() -> psycopg.Connection[Any]:
    """Create a database connection using PG_DATABASE_URL."""
    database_url = os.environ.get("PG_DATABASE_URL")
    if not database_url:
        raise ValueError("PG_DATABASE_URL environment variable is required")
    return psycopg.connect(database_url)


def setup_gcs_credentials() -> None:
    """Set up GCS credentials from MODEL_TRAINING_SA_KEY if GOOGLE_APPLICATION_CREDENTIALS is not set."""
    if os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        return

    sa_key = os.environ.get("MODEL_TRAINING_SA_KEY")
    if not sa_key:
        print("Warning: Neither GOOGLE_APPLICATION_CREDENTIALS nor MODEL_TRAINING_SA_KEY is set.")
        print("GCS downloads will use default credentials (e.g. gcloud auth).")
        return

    gcp_key_data = json.loads(sa_key)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as temp_key_file:
        temp_key_file.write(json.dumps(gcp_key_data).encode())
        temp_key_path = temp_key_file.name

    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = temp_key_path


def download_image_from_gcs(frame_uri: str) -> bytes:
    """Download image from GCS and return bytes."""
    if not frame_uri.startswith("gs://"):
        raise ValueError(f"Invalid GCS URI: {frame_uri}")

    parts = frame_uri[5:].split("/", 1)
    bucket_name = parts[0]
    blob_name = parts[1] if len(parts) > 1 else ""

    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    return blob.download_as_bytes()


def get_images_for_dataset(conn: psycopg.Connection[Any], dataset_name: str, limit: int) -> list[dict[str, Any]]:
    """Fetch images from a dataset that can be processed."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT i.image_id, i.frame_uri
            FROM machine_learning.images i
            WHERE i.dataset_name = %s
              AND i.frame_uri IS NOT NULL
            ORDER BY i.image_id
            LIMIT %s
            """,
            (dataset_name, limit),
        )
        return [{"image_id": row[0], "frame_uri": row[1]} for row in cur.fetchall()]


def main() -> None:
    """Main entrypoint."""
    parser = argparse.ArgumentParser(description="Run Gemini Agentic Vision on dataset images")
    parser.add_argument("--dataset-name", required=True, help="Dataset name in machine_learning.images")
    parser.add_argument(
        "--prompt",
        default=(
            "Analyze this image in detail. Describe what you see, identify objects, "
            "and provide any relevant measurements or counts. Use code execution to "
            "perform calculations if helpful."
        ),
        help="Prompt to send with each image",
    )
    parser.add_argument("--limit", type=int, default=100, help="Max number of images to process")
    parser.add_argument("--model", default="gemini-3-flash", help="Gemini model name")
    args = parser.parse_args()

    # Setup
    setup_gcs_credentials()
    conn = get_db_connection()

    try:
        # Read our own script content for reproducibility
        script_path = Path(__file__).resolve()
        script_content = script_path.read_text()

        # Create or get VLM source
        source_name = f"{args.model}-agentic-vision"
        vlm_source_id = get_or_create_vlm_source(
            conn,
            source_name,
            {"provider": "google", "model": args.model, "code_execution": True},
        )
        print(f"VLM source: {source_name} (id={vlm_source_id})")

        # Get images
        images = get_images_for_dataset(conn, args.dataset_name, args.limit)
        if not images:
            print(f"No images found in dataset '{args.dataset_name}'")
            return

        print(f"Found {len(images)} images to process")

        # Create run record
        run_name = f"{source_name}_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}"
        run_config = {
            "model": args.model,
            "dataset_name": args.dataset_name,
            "prompt": args.prompt,
            "limit": args.limit,
            "code_execution": True,
        }
        vlm_run_id = create_vlm_run(conn, run_name, vlm_source_id, run_config, script_content)
        print(f"Created vlm_run: {run_name} (id={vlm_run_id})")

        # Initialize Gemini client
        gemini_client = GeminiAgenticVisionClient(model=args.model)

        # Process images
        success_count = 0
        error_count = 0

        for i, img in enumerate(images):
            frame_uri = img["frame_uri"]
            print(f"[{i + 1}/{len(images)}] Processing {frame_uri}...", end=" ", flush=True)

            try:
                # Download image
                image_bytes = download_image_from_gcs(frame_uri)

                # Call Gemini agentic vision
                result = gemini_client.analyze_image(image_bytes, args.prompt)

                # Insert vlm_image (upsert)
                vlm_image_id = insert_vlm_image(conn, frame_uri)

                # Link run to image
                vlm_run_image_id = link_run_image(conn, vlm_run_id, vlm_image_id)

                # Store raw response
                insert_raw_response(conn, vlm_run_image_id, result.raw_response_text)

                # Store image description from text parts
                if result.text_parts:
                    description_text = "\n\n".join(result.text_parts)
                    code_artifacts = [{"code": step.code, "output": step.output} for step in result.code_execution_steps]
                    insert_image_description(
                        conn,
                        vlm_image_id,
                        vlm_source_id,
                        {
                            "dump_description": description_text,
                            "pile_contents": json.dumps(code_artifacts) if code_artifacts else None,
                        },
                    )

                success_count += 1
                print(f"OK ({len(result.text_parts)} text parts, {len(result.code_execution_steps)} code steps)")

            except Exception as e:
                error_count += 1
                print(f"ERROR: {e}")

        # Summary
        print("\nProcessing complete:")
        print(f"  Success: {success_count}")
        print(f"  Errors: {error_count}")
        print(f"  Run ID: {vlm_run_id}")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
