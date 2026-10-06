"""Build active-learning harness JSONL directly from annotation tables.

Outputs one JSON row per frame with object entries expected by
`run_active_learning_curve.py`.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

import asyncpg


@dataclass(frozen=True)
class AnnotationRow:
    annotation_id: int
    frame_uri: str
    class_name: str
    box_x1: int
    box_y1: int
    box_width: int
    box_height: int
    image_width: int
    image_height: int
    has_segmentation: bool
    camera_id: int | None


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _difficulty(row: AnnotationRow, class_freq: Counter[str], total: int) -> float:
    # Base uncertainty
    score = 0.15

    # Small objects are typically harder to segment.
    image_area = max(1, row.image_width * row.image_height)
    box_area = max(1, row.box_width * row.box_height)
    area_fraction = box_area / image_area
    if area_fraction < 0.01:
        score += 0.35
    elif area_fraction < 0.03:
        score += 0.20
    elif area_fraction < 0.07:
        score += 0.10

    # Missing segmentation in source annotations indicates harder examples.
    if not row.has_segmentation:
        score += 0.25

    # Rare classes are generally harder for few-shot correction loops.
    freq = class_freq[row.class_name]
    freq_ratio = freq / max(1, total)
    rarity = 1.0 - freq_ratio
    score += 0.25 * rarity

    return round(_clamp01(score), 6)


async def _fetch_annotations(
    conn: asyncpg.Connection,
    dataset_name: str,
    training_split: str | None,
    limit_frames: int | None,
) -> list[AnnotationRow]:
    split_clause = ""
    params: list[object] = [dataset_name]
    if training_split:
        split_clause = "AND aj.training_split = $2"
        params.append(training_split)

    frame_limit_sql = ""
    if limit_frames and limit_frames > 0:
        frame_limit_sql = f"LIMIT {int(limit_frames)}"

    query = f"""
        WITH sampled_frames AS (
            SELECT DISTINCT aj.frame_uri
            FROM machine_learning.annotations_joined aj
            WHERE aj.dataset_name = $1
              {split_clause}
            ORDER BY aj.frame_uri
            {frame_limit_sql}
        )
        SELECT
            aj.annotation_id,
            aj.frame_uri,
            aj.class_name,
            aj.box_x1,
            aj.box_y1,
            aj.box_width,
            aj.box_height,
            aj.image_width,
            aj.image_height,
            aj.segmentations IS NOT NULL AS has_segmentation,
            fe.camera_id
        FROM machine_learning.annotations_joined aj
        LEFT JOIN machine_learning.frame_events fe
            ON fe.id = aj.frame_event_id
        INNER JOIN sampled_frames sf
            ON sf.frame_uri = aj.frame_uri
        WHERE aj.dataset_name = $1
          {split_clause}
        ORDER BY aj.frame_uri, aj.annotation_id
    """
    records = await conn.fetch(query, *params)
    return [
        AnnotationRow(
            annotation_id=int(record["annotation_id"]),
            frame_uri=str(record["frame_uri"]),
            class_name=str(record["class_name"]),
            box_x1=int(record["box_x1"]),
            box_y1=int(record["box_y1"]),
            box_width=int(record["box_width"]),
            box_height=int(record["box_height"]),
            image_width=int(record["image_width"]),
            image_height=int(record["image_height"]),
            has_segmentation=bool(record["has_segmentation"]),
            camera_id=int(record["camera_id"]) if record["camera_id"] is not None else None,
        )
        for record in records
    ]


def _build_rows(rows: list[AnnotationRow]) -> list[dict]:
    class_freq = Counter(row.class_name for row in rows)
    total = len(rows)
    by_frame: dict[str, list[AnnotationRow]] = defaultdict(list)
    for row in rows:
        by_frame[row.frame_uri].append(row)

    output: list[dict] = []
    for frame_uri, frame_rows in by_frame.items():
        objects: list[dict] = []
        for row in frame_rows:
            x1 = row.box_x1
            y1 = row.box_y1
            x2 = row.box_x1 + row.box_width
            y2 = row.box_y1 + row.box_height
            objects.append(
                {
                    "object_id": str(row.annotation_id),
                    "class_name": row.class_name,
                    "difficulty": _difficulty(row, class_freq, total),
                    "camera_id": row.camera_id,
                    "bbox_xyxy_px": [x1, y1, x2, y2],
                    "image_size": [row.image_width, row.image_height],
                    "has_segmentation": row.has_segmentation,
                }
            )
        output.append({"frame_id": frame_uri, "objects": objects})
    return output


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build JSONL input for active-learning curve simulation.")
    parser.add_argument("--dataset-name", required=True, help="Dataset name from machine_learning.annotations_joined.")
    parser.add_argument("--output-jsonl", required=True, help="Output JSONL path.")
    parser.add_argument("--training-split", default=None, help="Optional split filter, e.g. train/val/test.")
    parser.add_argument("--limit-frames", type=int, default=None, help="Optional maximum number of frame_uris.")
    parser.add_argument(
        "--pg-database-url",
        default=None,
        help="Postgres connection URL. Defaults to PG_DATABASE_URL env var.",
    )
    return parser.parse_args()


async def _run() -> None:
    args = _parse_args()
    database_url = args.pg_database_url or os.environ.get("PG_DATABASE_URL")
    if not database_url:
        raise RuntimeError("PG_DATABASE_URL is required (or pass --pg-database-url).")

    conn = await asyncpg.connect(database_url)
    try:
        rows = await _fetch_annotations(
            conn=conn,
            dataset_name=str(args.dataset_name),
            training_split=str(args.training_split) if args.training_split else None,
            limit_frames=args.limit_frames,
        )
    finally:
        await conn.close()

    output_rows = _build_rows(rows)
    output_path = Path(args.output_jsonl)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w") as f:
        for row in output_rows:
            f.write(json.dumps(row) + "\n")

    print(f"Wrote {len(output_rows)} frames ({len(rows)} objects) to {output_path}")


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
