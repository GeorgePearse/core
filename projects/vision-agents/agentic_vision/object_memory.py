"""Object-level memory retrieval and background-memory writes."""

from __future__ import annotations

import json
import os
import re
import time
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

import modal
import numpy as np
import psycopg
import turbopuffer
from loguru import logger
from PIL import Image
from psycopg.rows import dict_row

DEFAULT_OBJECT_MEMORY_EMBEDDING_SOURCE = "dinov3-vith16plus-pretrain-lvd1689m"
DEFAULT_DINO_MODEL_NAME = "facebook/dinov2-base"  # fallback for local embedding
DEFAULT_QDRANT_DISTANCE = "Cosine"


def _sanitize_collection_name(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "_", value).strip("_")
    return cleaned[:200] or "object_memory"


@dataclass(frozen=True)
class ObjectNeighbor:
    """Nearest-neighbor annotation with metadata."""

    rank: int
    annotation_id: int
    distance: float
    proximity_score: float
    class_name: str
    dataset_name: str
    camera_id: int | None
    frame_event_id: str | None
    frame_uri: str
    box_x1: int
    box_y1: int
    box_width: int
    box_height: int
    box_area_px: int
    box_area_fraction: float
    image_width: int
    image_height: int
    inference_category_id: int
    training_split: str
    state: str
    has_segmentation: bool
    updated_timestamp: str


class ObjectMemoryRetriever:
    """Retrieve similar annotations using TurboPuffer ANN on object embeddings."""

    def __init__(
        self,
        dataset_name: str,
        embedding_source_name: str = DEFAULT_OBJECT_MEMORY_EMBEDDING_SOURCE,
    ) -> None:
        self.dataset_name = dataset_name
        self.embedding_source_name = embedding_source_name
        self._namespace: str | None = None
        self._client: turbopuffer.Turbopuffer | None = None
        self._enabled = False

        try:
            self._client = self._create_turbopuffer_client()
            self._namespace = self._resolve_namespace()
            self._enabled = bool(self._namespace)
            logger.info(
                "Object memory enabled | dataset={} source={} namespace={}",
                self.dataset_name,
                self.embedding_source_name,
                self._namespace,
            )
        except Exception as exc:
            logger.warning("Object memory disabled for dataset={}: {}", dataset_name, exc)

    def build_knn_dump(
        self,
        annotation_id: int,
        max_neighbors: int = 5,
        include_query: bool = False,
    ) -> str:
        """Return a JSON dump of nearest-neighbor metadata."""
        if not self._enabled:
            return "Object memory unavailable."

        neighbors = self.get_similar_annotations(
            annotation_id=annotation_id,
            max_neighbors=max_neighbors,
            include_query=include_query,
        )
        if not neighbors:
            return "No similar annotations found."

        payload = [asdict(neighbor) for neighbor in neighbors]
        return json.dumps(payload, indent=2, sort_keys=True)

    def get_similar_annotations(
        self,
        annotation_id: int,
        max_neighbors: int = 5,
        include_query: bool = False,
    ) -> list[ObjectNeighbor]:
        """Return nearest neighbors for an existing annotation id."""
        if not self._enabled or max_neighbors <= 0:
            return []

        query_embedding = self._load_embedding_for_annotation(annotation_id)
        if not query_embedding:
            logger.debug("No embedding found for annotation_id={}", annotation_id)
            return []

        candidates = self._query_neighbors(query_embedding, top_k=max(max_neighbors * 25, max_neighbors + 1))
        if not candidates:
            return []

        filtered: list[tuple[int, float]] = []
        for neighbor_id, distance in candidates:
            if not include_query and neighbor_id == annotation_id:
                continue
            filtered.append((neighbor_id, distance))
            if len(filtered) >= max_neighbors:
                break

        if not filtered:
            return []

        metadata_by_id = self._load_annotation_metadata([neighbor_id for neighbor_id, _ in filtered])

        neighbors: list[ObjectNeighbor] = []
        for idx, (neighbor_id, distance) in enumerate(filtered, start=1):
            metadata = metadata_by_id.get(neighbor_id)
            if metadata is None:
                continue
            neighbors.append(
                ObjectNeighbor(
                    rank=idx,
                    annotation_id=neighbor_id,
                    distance=distance,
                    proximity_score=1.0 - distance,
                    class_name=str(metadata["class_name"]),
                    dataset_name=str(metadata["dataset_name"]),
                    camera_id=metadata["camera_id"],
                    frame_event_id=str(metadata["frame_event_id"]) if metadata["frame_event_id"] is not None else None,
                    frame_uri=str(metadata["frame_uri"]),
                    box_x1=int(metadata["box_x1"]),
                    box_y1=int(metadata["box_y1"]),
                    box_width=int(metadata["box_width"]),
                    box_height=int(metadata["box_height"]),
                    box_area_px=int(metadata["box_width"]) * int(metadata["box_height"]),
                    box_area_fraction=self._box_area_fraction(
                        int(metadata["box_width"]),
                        int(metadata["box_height"]),
                        int(metadata["image_width"]),
                        int(metadata["image_height"]),
                    ),
                    image_width=int(metadata["image_width"]),
                    image_height=int(metadata["image_height"]),
                    inference_category_id=int(metadata["inference_category_id"]),
                    training_split=str(metadata["training_split"]),
                    state=str(metadata["state"]),
                    has_segmentation=bool(metadata["has_segmentation"]),
                    updated_timestamp=self._format_timestamp(metadata["updated_timestamp"]),
                )
            )
        return neighbors

    @staticmethod
    def _box_area_fraction(box_width: int, box_height: int, image_width: int, image_height: int) -> float:
        image_area = image_width * image_height
        if image_area <= 0:
            return 0.0
        return round((box_width * box_height) / image_area, 6)

    @staticmethod
    def _format_timestamp(value: Any) -> str:
        if isinstance(value, datetime):
            return value.isoformat()
        return str(value)

    def _create_turbopuffer_client(self) -> turbopuffer.Turbopuffer:
        api_key = os.environ.get("TURBOPUFFER_API_KEY")
        if not api_key:
            raise RuntimeError("TURBOPUFFER_API_KEY is required")
        return turbopuffer.Turbopuffer(api_key=api_key, region="gcp-us-central1")

    def _resolve_namespace(self) -> str:
        database_url = os.environ.get("PG_DATABASE_URL")
        if not database_url:
            raise RuntimeError("PG_DATABASE_URL is required")

        with psycopg.connect(database_url) as conn:
            with conn.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    """
                    SELECT tc.turbopuffer_namespace
                    FROM machine_learning.turbopuffer_connector tc
                    JOIN machine_learning.embedding_sources es ON es.id = tc.embedding_source_id
                    WHERE tc.dataset_name = %(dataset_name)s
                      AND lower(es.name) = lower(%(embedding_source_name)s)
                    LIMIT 1
                    """,
                    {
                        "dataset_name": self.dataset_name,
                        "embedding_source_name": self.embedding_source_name,
                    },
                )
                row = cursor.fetchone()
                if row and isinstance(row["turbopuffer_namespace"], str) and row["turbopuffer_namespace"]:
                    return row["turbopuffer_namespace"]

                cursor.execute(
                    """
                    SELECT tc.turbopuffer_namespace, es.name
                    FROM machine_learning.turbopuffer_connector tc
                    JOIN machine_learning.embedding_sources es ON es.id = tc.embedding_source_id
                    WHERE tc.dataset_name = %(dataset_name)s
                      AND (lower(es.name) LIKE 'dinov2%%' OR lower(es.name) LIKE 'dinov3%%')
                    ORDER BY es.id DESC
                    LIMIT 1
                    """,
                    {"dataset_name": self.dataset_name},
                )
                fallback = cursor.fetchone()
                if fallback and isinstance(fallback["turbopuffer_namespace"], str) and fallback["turbopuffer_namespace"]:
                    logger.info(
                        "Object memory source '{}' not found; using '{}' for dataset={}",
                        self.embedding_source_name,
                        fallback["name"],
                        self.dataset_name,
                    )
                    return fallback["turbopuffer_namespace"]

        raise RuntimeError(
            f"No TurboPuffer namespace found for dataset={self.dataset_name} "
            f"and embedding source={self.embedding_source_name}"
        )

    def _load_embedding_for_annotation(self, annotation_id: int) -> list[float]:
        assert self._client is not None
        assert self._namespace is not None
        ns = self._client.namespace(self._namespace)
        result = ns.query(
            filters=("And", [("id", "In", [annotation_id])]),  # type: ignore[arg-type]
            rank_by=("id", "asc"),
            top_k=1,
            include_attributes=True,
        )
        if not result.rows:
            return []
        vector = result.rows[0].vector
        if vector is None:
            return []
        return [float(value) for value in vector]

    def _query_neighbors(self, query_embedding: Sequence[float], top_k: int) -> list[tuple[int, float]]:
        assert self._client is not None
        assert self._namespace is not None
        ns = self._client.namespace(self._namespace)
        result = ns.query(
            rank_by=("vector", "ANN", [float(value) for value in query_embedding]),
            top_k=top_k,
            include_attributes=True,
        )
        if not result.rows:
            return []
        return [(int(row.id), float(row["$dist"])) for row in result.rows]

    def _load_annotation_metadata(self, annotation_ids: list[int]) -> dict[int, dict[str, Any]]:
        if not annotation_ids:
            return {}
        database_url = os.environ.get("PG_DATABASE_URL")
        if not database_url:
            raise RuntimeError("PG_DATABASE_URL is required")

        with psycopg.connect(database_url) as conn:
            with conn.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    """
                    SELECT
                        aj.annotation_id,
                        aj.class_name,
                        aj.dataset_name,
                        aj.frame_event_id,
                        aj.frame_uri,
                        aj.box_x1,
                        aj.box_y1,
                        aj.box_width,
                        aj.box_height,
                        aj.image_width,
                        aj.image_height,
                        aj.inference_category_id,
                        aj.training_split,
                        aj.state,
                        aj.updated_timestamp,
                        aj.segmentations IS NOT NULL AS has_segmentation,
                        fe.camera_id
                    FROM machine_learning.annotations_joined aj
                    LEFT JOIN machine_learning.frame_events fe ON fe.id = aj.frame_event_id
                    WHERE aj.dataset_name = %(dataset_name)s
                      AND aj.annotation_id = ANY(%(annotation_ids)s)
                    """,
                    {
                        "dataset_name": self.dataset_name,
                        "annotation_ids": annotation_ids,
                    },
                )
                rows = cursor.fetchall()
        return {int(row["annotation_id"]): dict(row) for row in rows}


@dataclass(frozen=True)
class BackgroundObjectObservation:
    """Single background object observation to persist in memory."""

    detection_id: int
    class_name: str
    confidence: float
    camera_id: int | None
    frame_uri: str | None
    dataset_name: str
    box_x1: int
    box_y1: int
    box_x2: int
    box_y2: int
    image_width: int
    image_height: int
    reason: str
    crop_bgr: np.ndarray
    source_stage: str | None = None
    source_text: str | None = None
    extra_metadata: dict[str, Any] | None = None


class ObjectMemoryBackgroundStore:
    """Persist background-object memory to TurboPuffer or local Qdrant."""

    _processor: Any | None = None
    _model: Any | None = None

    def __init__(
        self,
        dataset_name: str,
        embedding_source_name: str = DEFAULT_OBJECT_MEMORY_EMBEDDING_SOURCE,
        dino_model_name: str = DEFAULT_DINO_MODEL_NAME,
    ) -> None:
        self.dataset_name = dataset_name
        self.embedding_source_name = embedding_source_name
        self.dino_model_name = dino_model_name
        self._namespace: str | None = None
        self._turbopuffer_client: turbopuffer.Turbopuffer | None = None
        self._qdrant_client: Any | None = None
        self._qdrant_collection_name: str | None = None
        self._backend: str | None = None

        try:
            self._namespace = self._resolve_namespace()
        except Exception as exc:
            logger.info(f"Object memory namespace lookup unavailable for dataset={dataset_name}: {exc}")

        try:
            self._turbopuffer_client = self._create_turbopuffer_client()
            if self._namespace:
                self._backend = "turbopuffer"
        except Exception as exc:
            logger.info(f"TurboPuffer unavailable for background memory: {exc}")

        if self._backend is None:
            self._init_qdrant_backend()

    @property
    def backend_name(self) -> str:
        return self._backend or "unavailable"

    def store_background_observations(self, observations: Sequence[BackgroundObjectObservation]) -> dict[str, int | str]:
        if not observations:
            return {"stored": 0, "backend": self.backend_name}
        if self._backend is None:
            raise RuntimeError("No object-memory backend available (TurboPuffer or Qdrant required).")

        vectors = self._embed_observations(observations)
        if len(vectors) != len(observations):
            raise RuntimeError("Embedding generation returned unexpected vector count.")

        if self._backend == "turbopuffer":
            self._upsert_turbopuffer(observations, vectors)
        elif self._backend == "qdrant":
            self._upsert_qdrant(observations, vectors)
        else:
            raise RuntimeError(f"Unsupported backend: {self._backend}")

        return {"stored": len(observations), "backend": self._backend}

    def _create_turbopuffer_client(self) -> turbopuffer.Turbopuffer:
        api_key = os.environ.get("TURBOPUFFER_API_KEY")
        if not api_key:
            raise RuntimeError("TURBOPUFFER_API_KEY is required")
        return turbopuffer.Turbopuffer(api_key=api_key, region="gcp-us-central1")

    def _resolve_namespace(self) -> str:
        database_url = os.environ.get("PG_DATABASE_URL")
        if not database_url:
            raise RuntimeError("PG_DATABASE_URL is required")

        with psycopg.connect(database_url) as conn:
            with conn.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    """
                    SELECT tc.turbopuffer_namespace
                    FROM machine_learning.turbopuffer_connector tc
                    JOIN machine_learning.embedding_sources es ON es.id = tc.embedding_source_id
                    WHERE tc.dataset_name = %(dataset_name)s
                      AND (lower(es.name) LIKE 'dinov2%%' OR lower(es.name) LIKE 'dinov3%%')
                    ORDER BY es.id DESC
                    LIMIT 1
                    """,
                    {"dataset_name": self.dataset_name},
                )
                row = cursor.fetchone()
                if row and isinstance(row["turbopuffer_namespace"], str) and row["turbopuffer_namespace"]:
                    return row["turbopuffer_namespace"]
        raise RuntimeError(f"No TurboPuffer namespace found for dataset={self.dataset_name}")

    def _init_qdrant_backend(self) -> None:
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.models import Distance, VectorParams
        except Exception as exc:
            logger.warning(f"Qdrant unavailable for background memory fallback: {exc}")
            return

        storage_path = os.environ.get("OBJECT_MEMORY_QDRANT_PATH", "./qdrant_object_memory")
        collection_name = os.environ.get(
            "OBJECT_MEMORY_QDRANT_COLLECTION",
            _sanitize_collection_name(f"{self.dataset_name}_{self.embedding_source_name}_background"),
        )

        client = QdrantClient(path=storage_path)
        collections = [c.name for c in client.get_collections().collections]
        if collection_name not in collections:
            distance = Distance.COSINE if DEFAULT_QDRANT_DISTANCE == "Cosine" else Distance.DOT
            client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(size=768, distance=distance, on_disk=True),
            )
        self._qdrant_client = client
        self._qdrant_collection_name = collection_name
        self._backend = "qdrant"

    def _embed_observations(self, observations: Sequence[BackgroundObjectObservation]) -> list[list[float]]:
        """Generate embeddings using Modal embedding-calculator endpoint."""
        # Get the Modal embedding calculator
        try:
            embedding_calculator = modal.Cls.from_name("embedding-calculator", "EmbeddingCalculator")
            calculator_instance = embedding_calculator()
        except Exception as exc:
            logger.error(f"Failed to connect to Modal embedding-calculator: {exc}")
            raise RuntimeError(f"Modal embedding-calculator unavailable: {exc}")

        vectors: list[list[float]] = []
        for obs in observations:
            # Convert BGR to RGB PIL Image
            rgb = obs.crop_bgr[:, :, ::-1]
            pil_image = Image.fromarray(rgb)

            try:
                # Call Modal endpoint
                embedding = calculator_instance.embed_image.remote(pil_image)
                # embedding is a numpy array, convert to list of floats
                vectors.append([float(v) for v in embedding.flatten()])
            except Exception as exc:
                logger.warning(f"Failed to embed observation: {exc}")
                # Return zero vector as fallback
                vectors.append([0.0] * 768)  # DINOv3 ViT-H has 768-dim embeddings

        return vectors

    @staticmethod
    def _build_payload(observation: BackgroundObjectObservation) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "class_name": observation.class_name,
            "confidence": float(observation.confidence),
            "camera_id": observation.camera_id,
            "frame_uri": observation.frame_uri,
            "dataset_name": observation.dataset_name,
            "box_x1": observation.box_x1,
            "box_y1": observation.box_y1,
            "box_x2": observation.box_x2,
            "box_y2": observation.box_y2,
            "box_width": max(0, observation.box_x2 - observation.box_x1),
            "box_height": max(0, observation.box_y2 - observation.box_y1),
            "image_width": observation.image_width,
            "image_height": observation.image_height,
            "reason": observation.reason,
            "memory_type": "background_object",
            "created_at_epoch_s": int(time.time()),
            "source_stage": observation.source_stage,
            "source_text": observation.source_text,
        }
        if observation.extra_metadata:
            payload.update(observation.extra_metadata)
        return payload

    def _upsert_turbopuffer(self, observations: Sequence[BackgroundObjectObservation], vectors: Sequence[Sequence[float]]) -> None:
        assert self._turbopuffer_client is not None
        assert self._namespace is not None
        ns = self._turbopuffer_client.namespace(self._namespace)
        ids = [int(obs.detection_id) for obs in observations]
        payloads = [self._build_payload(obs) for obs in observations]
        documents: dict[str, Any] = {
            "id": ids,
            "vector": [[float(value) for value in vector] for vector in vectors],
        }
        for key in payloads[0]:
            documents[key] = [payload[key] for payload in payloads]
        # Specify schema for float fields to avoid type inference issues
        schema: dict[str, str] = {
            "confidence": "float",
        }
        ns.write(
            upsert_columns=documents,
            distance_metric="cosine_distance",
            schema=schema,
        )

    def _upsert_qdrant(self, observations: Sequence[BackgroundObjectObservation], vectors: Sequence[Sequence[float]]) -> None:
        assert self._qdrant_client is not None
        assert self._qdrant_collection_name is not None
        from qdrant_client.models import PointStruct

        points = []
        for obs, vector in zip(observations, vectors, strict=True):
            points.append(
                PointStruct(
                    id=int(obs.detection_id),
                    vector=[float(value) for value in vector],
                    payload=self._build_payload(obs),
                )
            )
        self._qdrant_client.upsert(collection_name=self._qdrant_collection_name, points=points)
