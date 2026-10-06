# type: ignore
"""Modal app for SAM3 inference with positive/negative point prompt support.

This deployment extends the base segment_boxes functionality to accept
per-box positive and negative point prompts for refined mask generation.
"""

from __future__ import annotations

import json
import math
import os
import tempfile
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Any

import modal
from loguru import logger

# Container paths
SAM3_REPO_DIR = Path("/opt/sam3")
MODELS_ROOT = Path("/opt/pipelines/models")
MODEL_VOLUME_MOUNT = "/root/artifacts"
CONTAINER_MODEL_URI_MAP_PATH = Path("/root/model_uris.yaml")

# Local paths for image building (read-only from core repo)
CORE_REPO_ROOT = Path("/home/georgepearse/core-worktrees/main")
LOCAL_SAM3_REPO_DIR = CORE_REPO_ROOT / "machine_learning/packages/sam3"
LOCAL_MODELS_DIR = CORE_REPO_ROOT / "lib/python/pipelines/pipelines/models"
LOCAL_MODEL_URI_MAP = CORE_REPO_ROOT / "backend/sam3_inference/sam3_inference/model_uris.yaml"

# Defaults
MODAL_TIMEOUT_SECONDS = 3600
MAX_INFERENCE_CONTAINERS = 5
SAM3_DEFAULT_HANDLER_NAME = os.getenv("SAM3_HANDLER_NAME", "premier_sam3")

# Build Modal image
image = (
    modal.Image.from_registry("nvcr.io/nvidia/cuda:12.6.0-devel-ubuntu22.04", add_python="3.12")
    .run_commands(
        "pip install torch==2.7.0 torchvision torchaudio --index-url https://download.pytorch.org/whl/cu126",
        "pip install google-cloud-storage pillow pyyaml loguru opencv-python",
    )
    .add_local_dir(LOCAL_SAM3_REPO_DIR, remote_path=str(SAM3_REPO_DIR), copy=True)
    .add_local_dir(LOCAL_MODELS_DIR, remote_path=str(MODELS_ROOT), copy=True)
    .add_local_file(str(LOCAL_MODEL_URI_MAP), remote_path=str(CONTAINER_MODEL_URI_MAP_PATH), copy=True)
    .run_commands(f'cd {SAM3_REPO_DIR} && pip install -e ".[train,dev,notebooks]"')
)

app = modal.App(name="sam3-vision-agents", image=image)

model_volume = modal.Volume.from_name(
    "sam3-checkpoint-cache",
    environment_name="main",
)


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _configure_gcp_credentials() -> str:
    """Configure GOOGLE_APPLICATION_CREDENTIALS from MODEL_TRAINING_SA_KEY."""
    sa_key = os.environ.get("MODEL_TRAINING_SA_KEY")
    if not sa_key:
        raise ValueError("MODEL_TRAINING_SA_KEY environment variable is missing.")

    gcp_key_data = json.loads(sa_key)
    with tempfile.NamedTemporaryFile(delete=False) as temp_key_file:
        temp_key_file.write(json.dumps(gcp_key_data).encode())
        temp_key_path = temp_key_file.name

    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = temp_key_path
    return temp_key_path


def _parse_gcs_uri(uri: str) -> tuple[str, str]:
    """Split a GCS URI into bucket and blob path."""
    if not uri.startswith("gs://"):
        raise ValueError(f"Expected GCS URI, got {uri}")
    bucket, _, blob = uri[5:].partition("/")
    if not bucket or not blob:
        raise ValueError(f"Invalid GCS URI: {uri}")
    return bucket, blob


def _download_gcs_image(frame_uri: str, destination: Path) -> None:
    """Download the GCS object at frame_uri to destination."""
    from google.cloud import storage

    bucket_name, blob_name = _parse_gcs_uri(frame_uri)
    client = storage.Client()
    blob = client.bucket(bucket_name).blob(blob_name)
    blob.download_to_filename(destination)


@lru_cache(maxsize=1)
def _load_model_uri_map() -> dict[str, str]:
    """Load model_name -> checkpoint URI mapping from the package YAML."""
    import yaml

    path = CONTAINER_MODEL_URI_MAP_PATH
    if not path.exists():
        return {}

    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise ValueError(f"Model URI map must contain a YAML dictionary: {path}")

    mapping: dict[str, str] = {}
    for model_name, model_uri in payload.items():
        if isinstance(model_name, str) and isinstance(model_uri, str):
            cleaned_name = model_name.strip()
            cleaned_uri = model_uri.strip()
            if cleaned_name and cleaned_uri:
                mapping[cleaned_name] = cleaned_uri
    return mapping


def _checkpoint_path_for_model(model_name: str) -> str:
    """Resolve a model-specific checkpoint URI from map, with legacy fallback."""
    mapped_uri = _load_model_uri_map().get(model_name)
    if mapped_uri:
        return mapped_uri
    return f"gs://binit-models/sam3_checkpoints/{model_name}/checkpoint.pt"


def _download_gcs_blob(source_uri: str, destination: Path) -> None:
    """Download a GCS blob to a local destination path."""
    from google.cloud import storage

    bucket_name, blob_name = _parse_gcs_uri(source_uri)
    destination.parent.mkdir(parents=True, exist_ok=True)
    client = storage.Client()
    blob = client.bucket(bucket_name).blob(blob_name)
    blob.download_to_filename(destination)


def _resolve_checkpoint_path(checkpoint_path: str | None, model_name: str) -> Path:
    """Resolve a GCS checkpoint URI into the mounted volume and download when missing."""
    if checkpoint_path is None:
        checkpoint_path = os.getenv("SAM3_CHECKPOINT_PATH") or _checkpoint_path_for_model(model_name)
    if not checkpoint_path:
        raise ValueError("checkpoint_path is required (or set SAM3_CHECKPOINT_PATH).")
    if not checkpoint_path.startswith("gs://"):
        raise ValueError(f"checkpoint_path must be a GCS URI, got: {checkpoint_path}")

    _, blob_name = _parse_gcs_uri(checkpoint_path)
    candidate = Path(MODEL_VOLUME_MOUNT) / blob_name

    if candidate.exists():
        return candidate

    _download_gcs_blob(checkpoint_path, candidate)
    model_volume.commit()

    if not candidate.exists():
        raise FileNotFoundError(f"Checkpoint download failed for {checkpoint_path}; expected local path {candidate}")

    return candidate


def _maybe_convert_checkpoint(checkpoint_path: Path) -> Path:
    """Convert training checkpoint format to SAM3 detector state dict if needed."""
    from collections import OrderedDict

    import torch

    payload = torch.load(checkpoint_path, map_location="cpu")
    if not isinstance(payload, dict) or "model" not in payload:
        return checkpoint_path
    model_state = payload.get("model")
    if not isinstance(model_state, dict):
        return checkpoint_path

    converted_state = OrderedDict(("detector." + key, value) for key, value in model_state.items())
    with tempfile.NamedTemporaryFile(suffix="_converted.pt", delete=False) as temp_file:
        converted_path = Path(temp_file.name)
    torch.save(converted_state, converted_path)
    return converted_path


def _bbox_points(bbox: tuple[float, float, float, float]) -> list[tuple[float, float]]:
    """Return a rectangle polygon from a normalized bbox."""
    x0, y0, x1, y1 = bbox
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def _pairwise_iou_xyxy(boxes1, boxes2):
    """Compute pairwise IoU between two sets of xyxy boxes."""
    import torch

    if boxes1.numel() == 0 or boxes2.numel() == 0:
        return boxes1.new_zeros((boxes1.shape[0], boxes2.shape[0]))

    x0 = torch.maximum(boxes1[:, None, 0], boxes2[None, :, 0])
    y0 = torch.maximum(boxes1[:, None, 1], boxes2[None, :, 1])
    x1 = torch.minimum(boxes1[:, None, 2], boxes2[None, :, 2])
    y1 = torch.minimum(boxes1[:, None, 3], boxes2[None, :, 3])

    inter = (x1 - x0).clamp(min=0) * (y1 - y0).clamp(min=0)
    area1 = (boxes1[:, 2] - boxes1[:, 0]).clamp(min=0) * (boxes1[:, 3] - boxes1[:, 1]).clamp(min=0)
    area2 = (boxes2[:, 2] - boxes2[:, 0]).clamp(min=0) * (boxes2[:, 3] - boxes2[:, 1]).clamp(min=0)
    union = area1[:, None] + area2[None, :] - inter
    return torch.where(union > 0, inter / union, torch.zeros_like(inter))


def _polygon_area(points: list[tuple[int, int]]) -> float:
    """Compute signed polygon area via shoelace."""
    if len(points) < 3:
        return 0.0
    area = 0.0
    for index in range(len(points)):
        x0, y0 = points[index]
        x1, y1 = points[(index + 1) % len(points)]
        area += float(x0 * y1 - x1 * y0)
    return 0.5 * area


def _remove_consecutive_duplicates(points: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Remove duplicate adjacent vertices while preserving order."""
    if not points:
        return points
    deduped = [points[0]]
    for point in points[1:]:
        if point != deduped[-1]:
            deduped.append(point)
    if len(deduped) > 1 and deduped[0] == deduped[-1]:
        deduped.pop()
    return deduped


def _remove_collinear_points(points: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Drop exactly collinear points to reduce size without changing shape."""
    if len(points) < 4:
        return points

    simplified = points[:]
    changed = True
    while changed and len(simplified) >= 4:
        changed = False
        next_points: list[tuple[int, int]] = []
        for index in range(len(simplified)):
            prev_point = simplified[index - 1]
            curr_point = simplified[index]
            next_point = simplified[(index + 1) % len(simplified)]

            cross = (curr_point[0] - prev_point[0]) * (next_point[1] - prev_point[1]) - (curr_point[1] - prev_point[1]) * (
                next_point[0] - prev_point[0]
            )
            if cross == 0:
                changed = True
                continue
            next_points.append(curr_point)
        simplified = next_points

    return simplified


def _point_line_distance(point: tuple[int, int], start: tuple[int, int], end: tuple[int, int]) -> float:
    """Distance from point to line segment."""
    px, py = point
    sx, sy = start
    ex, ey = end

    dx = ex - sx
    dy = ey - sy
    if dx == 0 and dy == 0:
        return math.hypot(px - sx, py - sy)

    t = ((px - sx) * dx + (py - sy) * dy) / float(dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    proj_x = sx + t * dx
    proj_y = sy + t * dy
    return math.hypot(px - proj_x, py - proj_y)


def _rdp(points: list[tuple[int, int]], epsilon: float) -> list[tuple[int, int]]:
    """Ramer-Douglas-Peucker simplification for ordered points."""
    if len(points) <= 2:
        return points

    start = points[0]
    end = points[-1]
    max_distance = -1.0
    max_index = -1

    for index in range(1, len(points) - 1):
        distance = _point_line_distance(points[index], start, end)
        if distance > max_distance:
            max_distance = distance
            max_index = index

    if max_distance <= epsilon or max_index < 0:
        return [start, end]

    left = _rdp(points[: max_index + 1], epsilon)
    right = _rdp(points[max_index:], epsilon)
    return left[:-1] + right


def _downsample_polygon(points: list[tuple[int, int]], max_points: int = 4096) -> list[tuple[int, int]]:
    """Downsample while preserving shape as much as possible."""
    simplified = _remove_collinear_points(_remove_consecutive_duplicates(points))
    if len(simplified) <= max_points:
        return simplified

    epsilon = 0.5
    while len(simplified) > max_points and epsilon <= 8.0:
        closed = [*simplified, simplified[0]]
        simplified = _rdp(closed, epsilon)
        if len(simplified) >= 2 and simplified[0] == simplified[-1]:
            simplified = simplified[:-1]
        simplified = _remove_collinear_points(_remove_consecutive_duplicates(simplified))
        epsilon *= 1.5

    if len(simplified) > max_points:
        step = max(1, len(simplified) // max_points)
        simplified = simplified[::step]

    return simplified


def _extract_largest_boundary_polygon(mask_np) -> list[tuple[int, int]]:
    """Extract the largest ordered mask boundary polygon with concavity preserved."""
    import numpy as np

    height, width = mask_np.shape
    edges: dict[tuple[int, int], list[tuple[int, int]]] = defaultdict(list)

    for y in range(height):
        xs = np.nonzero(mask_np[y])[0].tolist()
        for x in xs:
            if y == 0 or not mask_np[y - 1, x]:
                edges[(x, y)].append((x + 1, y))
            if x == width - 1 or not mask_np[y, x + 1]:
                edges[(x + 1, y)].append((x + 1, y + 1))
            if y == height - 1 or not mask_np[y + 1, x]:
                edges[(x + 1, y + 1)].append((x, y + 1))
            if x == 0 or not mask_np[y, x - 1]:
                edges[(x, y + 1)].append((x, y))

    if not edges:
        return []

    visited: set[tuple[tuple[int, int], tuple[int, int]]] = set()
    loops: list[list[tuple[int, int]]] = []

    for start, neighbors in edges.items():
        for end in neighbors:
            first_edge = (start, end)
            if first_edge in visited:
                continue

            edge = first_edge
            loop = [start]
            while True:
                edge_start, edge_end = edge
                visited.add(edge)
                loop.append(edge_end)

                next_candidates = [candidate for candidate in edges.get(edge_end, []) if (edge_end, candidate) not in visited]
                if not next_candidates:
                    break

                if len(next_candidates) > 1 and edge_start in next_candidates:
                    next_candidates = [candidate for candidate in next_candidates if candidate != edge_start] or next_candidates

                edge = (edge_end, next_candidates[0])
                if edge == first_edge:
                    break

            loop = _remove_collinear_points(_remove_consecutive_duplicates(loop))
            if len(loop) >= 3:
                loops.append(loop)

    if not loops:
        return []

    return max(loops, key=lambda points: abs(_polygon_area(points)))


def _mask_to_polygon_points(
    mask,
    width: int,
    height: int,
    fallback_bbox: tuple[float, float, float, float],
) -> list[tuple[float, float]]:
    """Convert a predicted binary mask to normalized polygon points."""
    mask_np = mask.detach().cpu().numpy().astype(bool)
    if mask_np.ndim == 3:
        mask_np = mask_np[0]
    if mask_np.ndim != 2 or not mask_np.any():
        return _bbox_points(fallback_bbox)

    polygon = _extract_largest_boundary_polygon(mask_np)
    if len(polygon) < 3:
        return _bbox_points(fallback_bbox)
    polygon = _downsample_polygon(polygon, max_points=4096)

    points: list[tuple[float, float]] = []
    for x, y in polygon:
        px = max(0.0, min(float(x) / max(width, 1), 1.0))
        py = max(0.0, min(float(y) / max(height, 1), 1.0))
        points.append((px, py))

    return points if len(points) >= 3 else _bbox_points(fallback_bbox)


# ---------------------------------------------------------------------------
# Main inference function with point prompt support
# ---------------------------------------------------------------------------


@app.function(
    gpu=os.getenv("MODAL_GPU_TYPE", "A10G"),
    timeout=MODAL_TIMEOUT_SECONDS,
    max_containers=MAX_INFERENCE_CONTAINERS,
    volumes={MODEL_VOLUME_MOUNT: model_volume},
    secrets=[modal.Secret.from_name("model-training", environment_name="main")],
    retries=0,
)
def segment_boxes_with_points(
    frame_uri: str,
    boxes: list[list[float]],
    handler_name: str,
    positive_points: list[list[list[float]]] | None = None,
    negative_points: list[list[list[float]]] | None = None,
) -> list[dict[str, Any]]:
    """Generate segmentation masks for bounding boxes with optional point prompts.

    Args:
        frame_uri: GCS URI for the frame image.
        boxes: List of [x1, y1, x2, y2] bounding boxes in normalized [0, 1] coords.
        handler_name: Model name from model_uris.yaml (e.g. "premier_sam3").
        positive_points: Per-box list of positive point prompts [[x, y], ...] in [0, 1] coords.
            Format: positive_points[box_idx] = [[x1, y1], [x2, y2], ...]
        negative_points: Per-box list of negative point prompts [[x, y], ...] in [0, 1] coords.
            Format: negative_points[box_idx] = [[x1, y1], [x2, y2], ...]

    Returns:
        List of result dicts with keys: label, bbox, points, score, segmentation_area.
    """
    import sam3.model.sam3_image_processor as sam3_image_processor
    import torch
    from PIL import Image, ImageOps
    from sam3.model.sam3_image_processor import Sam3Processor
    from sam3.model_builder import build_sam3_image_model

    sam3_image_processor.PILImage = Image.Image

    resolved_handler_name = handler_name.strip()
    if not resolved_handler_name:
        raise ValueError("handler_name must be provided.")

    # Initialize point lists if not provided
    if positive_points is None:
        positive_points = [[] for _ in boxes]
    if negative_points is None:
        negative_points = [[] for _ in boxes]

    # Resolve checkpoint directly from model_uris.yaml
    direct_checkpoint_uri = _load_model_uri_map().get(resolved_handler_name)
    if direct_checkpoint_uri:
        resolved_model_name = resolved_handler_name
    else:
        # Fallback to legacy path
        direct_checkpoint_uri = _checkpoint_path_for_model(resolved_handler_name)
        resolved_model_name = resolved_handler_name

    logger.info(
        f"SAM3 segment_boxes_with_points: model={resolved_model_name}, "
        f"frame={frame_uri}, boxes={len(boxes)}, "
        f"has_positive_points={any(positive_points)}, has_negative_points={any(negative_points)}"
    )

    temp_key_path: str | None = None
    image_path: Path | None = None
    converted_checkpoint: Path | None = None
    try:
        temp_key_path = _configure_gcp_credentials()
        with tempfile.NamedTemporaryFile(suffix=Path(frame_uri).suffix or ".jpg", delete=False) as temp_image:
            image_path = Path(temp_image.name)
        _download_gcs_image(frame_uri, image_path)

        image = ImageOps.exif_transpose(Image.open(image_path)).convert("RGB")
        width, height = image.size

        checkpoint = _resolve_checkpoint_path(direct_checkpoint_uri, resolved_model_name)
        converted_checkpoint = _maybe_convert_checkpoint(checkpoint)

        device = "cuda" if torch.cuda.is_available() else "cpu"
        model = build_sam3_image_model(
            bpe_path=str(SAM3_REPO_DIR / "sam3" / "assets" / "bpe_simple_vocab_16e6.txt.gz"),
            checkpoint_path=str(converted_checkpoint),
            load_from_hf=False,
            device=device,
            eval_mode=True,
            enable_segmentation=True,
        )
        processor = Sam3Processor(model=model, device=device, confidence_threshold=0.01)

        with torch.autocast(device_type="cuda", dtype=torch.bfloat16, enabled=torch.cuda.is_available()):
            state = processor.set_image(image)
            results: list[dict[str, Any]] = []

            for idx, box in enumerate(boxes):
                x1, y1, x2, y2 = float(box[0]), float(box[1]), float(box[2]), float(box[3])
                fallback_bbox = (x1, y1, x2, y2)
                fallback_points = _bbox_points(fallback_bbox)

                # Convert xyxy normalized to cxcywh normalized for add_geometric_prompt
                cx = (x1 + x2) / 2.0
                cy = (y1 + y2) / 2.0
                bw = x2 - x1
                bh = y2 - y1

                if bw <= 0 or bh <= 0:
                    results.append({
                        "label": "box",
                        "bbox": fallback_bbox,
                        "points": fallback_points,
                        "score": 0.0,
                        "segmentation_area": 0.0,
                    })
                    continue

                try:
                    processor.reset_all_prompts(state)

                    # Add box prompt
                    state = processor.add_geometric_prompt(
                        box=[cx, cy, bw, bh],
                        label=True,
                        state=state,
                    )

                    # Add point prompts if provided
                    box_positive_points = positive_points[idx] if idx < len(positive_points) else []
                    box_negative_points = negative_points[idx] if idx < len(negative_points) else []

                    if box_positive_points or box_negative_points:
                        all_points = []
                        all_labels = []

                        for pt in box_positive_points:
                            all_points.append([float(pt[0]), float(pt[1])])
                            all_labels.append(1)  # positive

                        for pt in box_negative_points:
                            all_points.append([float(pt[0]), float(pt[1])])
                            all_labels.append(0)  # negative

                        if all_points:
                            # Shape: [num_points, batch_size=1, 2]
                            points_tensor = torch.tensor(
                                all_points, device=device, dtype=torch.float32
                            ).unsqueeze(1)
                            # Shape: [num_points, batch_size=1]
                            labels_tensor = torch.tensor(
                                all_labels, device=device, dtype=torch.long
                            ).unsqueeze(1)

                            # Append points to the existing geometric prompt
                            geometric_prompt = state.get("geometric_prompt")
                            if geometric_prompt is not None:
                                geometric_prompt.append_points(points_tensor, labels_tensor)
                                # Re-run inference with combined box + point prompts
                                state = processor._forward_grounding(state)

                    masks = state.get("masks")
                    detected_boxes = state.get("boxes")
                    scores = state.get("scores")

                    if masks is None or detected_boxes is None or scores is None or masks.shape[0] == 0:
                        results.append({
                            "label": "box",
                            "bbox": fallback_bbox,
                            "points": fallback_points,
                            "score": 0.0,
                            "segmentation_area": 0.0,
                        })
                        continue

                    # Pick the detection with highest IoU to our input box
                    input_box_px = torch.tensor(
                        [[x1 * width, y1 * height, x2 * width, y2 * height]],
                        dtype=torch.float32,
                    )
                    det_boxes_cpu = detected_boxes.detach().cpu().to(dtype=torch.float32)
                    ious = _pairwise_iou_xyxy(input_box_px, det_boxes_cpu).squeeze(0)
                    best_idx = int(ious.argmax().item())

                    mask_tensor = masks[best_idx].detach().cpu()
                    if mask_tensor.ndim == 3:
                        mask_tensor = mask_tensor[0]

                    segmentation_area = float(mask_tensor.float().mean().item())
                    points = _mask_to_polygon_points(mask_tensor, width, height, fallback_bbox)
                    results.append({
                        "label": "box",
                        "bbox": fallback_bbox,
                        "points": points,
                        "score": float(scores[best_idx].item()),
                        "segmentation_area": segmentation_area,
                    })
                except Exception as exc:
                    logger.warning(f"SAM3 segmentation failed for box {box}: {exc}")
                    results.append({
                        "label": "box",
                        "bbox": fallback_bbox,
                        "points": fallback_points,
                        "score": 0.0,
                        "segmentation_area": 0.0,
                    })

                if torch.cuda.is_available():
                    torch.cuda.empty_cache()

        logger.info(f"SAM3 segment_boxes_with_points complete: {len(results)} masks for {len(boxes)} boxes")
        return results
    finally:
        if temp_key_path:
            Path(temp_key_path).unlink(missing_ok=True)
        if image_path:
            image_path.unlink(missing_ok=True)
        if converted_checkpoint:
            converted_checkpoint.unlink(missing_ok=True)


@app.local_entrypoint()
def main(
    frame_uri: str = "gs://binit-images-prod/test.jpg",
    handler_name: str = SAM3_DEFAULT_HANDLER_NAME,
):
    """Test entrypoint for local development."""
    boxes = [[0.1, 0.1, 0.5, 0.5]]
    positive_points = [[[0.3, 0.3]]]
    negative_points = [[]]

    results = segment_boxes_with_points.remote(
        frame_uri=frame_uri,
        boxes=boxes,
        handler_name=handler_name,
        positive_points=positive_points,
        negative_points=negative_points,
    )
    for i, result in enumerate(results):
        print(f"Box {i}: score={result['score']:.3f}, area={result['segmentation_area']:.4f}")
