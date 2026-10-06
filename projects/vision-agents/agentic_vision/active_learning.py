"""Active learning components for minimal-annotation instance segmentation.

This module provides uncertainty estimation, budget management, and knowledge
tracking for active learning experiments.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import numpy as np
from loguru import logger


class AnnotationStrategy(Enum):
    """Strategies for selecting which objects to annotate."""

    UNCERTAINTY_SAMPLING = "uncertainty"  # Annotate highest uncertainty first
    RANDOM_SAMPLING = "random"  # Baseline: random selection
    DIVERSITY_SAMPLING = "diversity"  # Spread annotations across embedding space
    CONFIDENCE_THRESHOLD = "threshold"  # Annotate when confidence below threshold


@dataclass
class ObjectUncertainty:
    """Uncertainty/confidence scores for a detected object.

    Combines multiple signals to estimate how confident the system is
    in its detection, classification, and segmentation of an object.
    """

    # Detection confidence (from Qwen or Gemini)
    detection_confidence: float = 0.5

    # Classification confidence
    classification_confidence: float = 0.5

    # How similar is this to nearest annotated example?
    # Lower distance = higher confidence (we've seen similar objects)
    knn_distance: float = 1.0
    knn_neighbor_count: int = 0

    # Cross-model consistency (if multiple VLMs available)
    cross_model_iou: float | None = None  # IoU between Qwen and Gemini boxes
    cross_model_label_agreement: bool = False

    # Segmentation quality (if segmentation attempted)
    segmentation_confidence: float | None = None
    mask_area_ratio: float | None = None  # mask_area / box_area

    # Combined uncertainty score (0 = certain, 1 = uncertain)
    overall_uncertainty: float = field(init=False)

    # Reason for uncertainty (human-readable)
    uncertainty_reasons: list[str] = field(default_factory=list)

    def __post_init__(self):
        """Calculate overall uncertainty from component scores."""
        # Normalize KNN distance to [0, 1] (0 = very close/high confidence)
        # Typical KNN distances in TurboPuffer are 0.1-0.5
        normalized_knn = min(self.knn_distance * 2, 1.0)

        # Start with detection and classification confidence
        # Invert so higher = more uncertain
        detection_uncertainty = 1.0 - self.detection_confidence
        classification_uncertainty = 1.0 - self.classification_confidence

        # Combine with weights
        weights = {
            "detection": 0.25,
            "classification": 0.25,
            "knn": 0.30,
            "cross_model": 0.10,
            "segmentation": 0.10,
        }

        components = [
            (detection_uncertainty, weights["detection"]),
            (classification_uncertainty, weights["classification"]),
            (normalized_knn, weights["knn"]),
        ]

        # Add cross-model consistency if available
        if self.cross_model_iou is not None:
            # IoU < 0.5 suggests models disagree = more uncertain
            cross_model_uncertainty = max(0.0, 1.0 - self.cross_model_iou * 2)
            components.append((cross_model_uncertainty, weights["cross_model"]))

        # Add segmentation quality if available
        if self.segmentation_confidence is not None:
            seg_uncertainty = 1.0 - self.segmentation_confidence
            components.append((seg_uncertainty, weights["segmentation"]))

        # Weighted average
        total_weight = sum(w for _, w in components)
        if total_weight > 0:
            self.overall_uncertainty = sum(score * weight for score, weight in components) / total_weight
        else:
            self.overall_uncertainty = 0.5

        # Generate human-readable reasons
        self._generate_uncertainty_reasons()

    def _generate_uncertainty_reasons(self) -> None:
        """Generate human-readable explanations for uncertainty."""
        reasons = []

        if self.detection_confidence < 0.6:
            reasons.append(f"low detection confidence ({self.detection_confidence:.2f})")

        if self.classification_confidence < 0.6:
            reasons.append(f"low classification confidence ({self.classification_confidence:.2f})")

        if self.knn_distance > 0.4:
            reasons.append(f"no similar examples in database (distance={self.knn_distance:.2f})")

        if self.cross_model_iou is not None and self.cross_model_iou < 0.5:
            reasons.append(f"models disagree on location (IoU={self.cross_model_iou:.2f})")

        if self.segmentation_confidence is not None and self.segmentation_confidence < 0.6:
            reasons.append(f"poor segmentation quality ({self.segmentation_confidence:.2f})")

        self.uncertainty_reasons = reasons

    def should_request_annotation(self, threshold: float = 0.7) -> bool:
        """Determine if this object should be human-annotated.

        Args:
            threshold: Uncertainty threshold above which to request annotation

        Returns:
            True if human annotation is recommended
        """
        return self.overall_uncertainty > threshold

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "detection_confidence": self.detection_confidence,
            "classification_confidence": self.classification_confidence,
            "knn_distance": self.knn_distance,
            "knn_neighbor_count": self.knn_neighbor_count,
            "cross_model_iou": self.cross_model_iou,
            "cross_model_label_agreement": self.cross_model_label_agreement,
            "segmentation_confidence": self.segmentation_confidence,
            "mask_area_ratio": self.mask_area_ratio,
            "overall_uncertainty": self.overall_uncertainty,
            "uncertainty_reasons": self.uncertainty_reasons,
        }


@dataclass
class AnnotatedExample:
    """A human-annotated example stored in the knowledge base."""

    annotation_id: int | None = None
    class_name: str = ""
    box: tuple[float, float, float, float] = (0, 0, 0, 0)  # x1, y1, x2, y2
    segmentation: list[tuple[float, float]] = field(default_factory=list)
    embedding: list[float] = field(default_factory=list)
    image_uri: str = ""
    camera_id: int | None = None

    # Metadata for analysis
    annotation_timestamp: str = ""
    source: str = "human"  # "human", "synthetic", "inferred"


class KnowledgeBase:
    """Maintains accumulated knowledge from annotations.

    Stores annotated examples and provides retrieval capabilities
    for bootstrapping the system on new images.
    """

    def __init__(self, dataset_name: str | None = None):
        self.dataset_name = dataset_name
        self.examples: list[AnnotatedExample] = []
        self.class_examples: dict[str, list[AnnotatedExample]] = {}
        self._retriever = None

        if dataset_name:
            try:
                from agentic_vision.object_memory import ObjectMemoryRetriever

                self._retriever = ObjectMemoryRetriever(dataset_name)
            except Exception as exc:
                logger.warning(f"Could not initialize KNN retriever: {exc}")

    def add_example(self, example: AnnotatedExample) -> None:
        """Add an annotated example to the knowledge base."""
        self.examples.append(example)

        # Index by class
        if example.class_name not in self.class_examples:
            self.class_examples[example.class_name] = []
        self.class_examples[example.class_name].append(example)

        logger.debug(
            f"Added example to knowledge base: {example.class_name} (total: {len(self.examples)} examples, {len(self.class_examples)} classes)"
        )

    def query_similar(
        self,
        annotation_id: int,
        max_neighbors: int = 5,
    ) -> list[dict[str, Any]]:
        """Query for similar examples via KNN.

        Returns:
            List of neighbor metadata dicts
        """
        if self._retriever is None:
            return []

        try:
            from agentic_vision.object_memory import ObjectNeighbor

            neighbors = self._retriever.get_similar_annotations(
                annotation_id=annotation_id,
                max_neighbors=max_neighbors,
                include_query=False,
            )
            return [n.__dict__ if isinstance(n, ObjectNeighbor) else n for n in neighbors]
        except Exception as exc:
            logger.warning(f"KNN query failed: {exc}")
            return []

    def estimate_uncertainty_for_detection(
        self,
        box: tuple[float, float, float, float],
        label: str,
    ) -> ObjectUncertainty:
        """Estimate uncertainty for a detected object using knowledge base.

        This is used when we don't have an annotation_id yet (new detection).
        We estimate based on class-level knowledge and spatial context.
        """
        uncertainty = ObjectUncertainty()

        # If we've seen this class before, we're more confident
        if label in self.class_examples:
            class_count = len(self.class_examples[label])
            # More examples = higher confidence (up to a point)
            uncertainty.classification_confidence = min(0.95, 0.5 + class_count * 0.05)
            uncertainty.knn_neighbor_count = class_count
            # Fake distance based on count
            uncertainty.knn_distance = max(0.1, 0.5 - class_count * 0.02)
        else:
            # Never seen this class
            uncertainty.classification_confidence = 0.3
            uncertainty.knn_distance = 1.0
            uncertainty.uncertainty_reasons.append(f"never seen class '{label}' before")

        return uncertainty

    def get_bootstrap_examples(
        self,
        n: int,
        strategy: str = "diverse",
    ) -> list[AnnotatedExample]:
        """Get N examples for bootstrapping.

        Strategies:
        - "random": Random selection
        - "diverse": Spread across different classes
        - "common": Most common classes first
        """
        if not self.examples:
            return []

        if strategy == "random":
            import random

            return random.sample(self.examples, min(n, len(self.examples)))

        elif strategy == "diverse":
            # Select from each class proportionally
            selected = []
            classes = list(self.class_examples.keys())
            per_class = max(1, n // len(classes))

            for class_name in classes:
                examples = self.class_examples[class_name]
                selected.extend(examples[:per_class])
                if len(selected) >= n:
                    break

            return selected[:n]

        elif strategy == "common":
            # Sort by class frequency
            sorted_classes = sorted(
                self.class_examples.items(),
                key=lambda x: len(x[1]),
                reverse=True,
            )
            selected = []
            for class_name, examples in sorted_classes:
                selected.extend(examples[: max(1, n // len(sorted_classes))])
                if len(selected) >= n:
                    break
            return selected[:n]

        return self.examples[:n]

    def to_dict(self) -> dict[str, Any]:
        """Serialize knowledge base state."""
        return {
            "dataset_name": self.dataset_name,
            "total_examples": len(self.examples),
            "classes": {name: len(examples) for name, examples in self.class_examples.items()},
        }


class AnnotationBudgetManager:
    """Manages the limited budget of human annotations.

    Tracks usage, enforces limits, and implements selection strategies
    for which objects to annotate.
    """

    def __init__(
        self,
        total_budget: int = 50,
        strategy: AnnotationStrategy = AnnotationStrategy.UNCERTAINTY_SAMPLING,
        uncertainty_threshold: float = 0.7,
    ):
        self.total_budget = total_budget
        self.used_budget = 0
        self.strategy = strategy
        self.uncertainty_threshold = uncertainty_threshold

        # Track what we've annotated
        self.annotated_objects: list[dict[str, Any]] = []

        # Pending queue for uncertainty sampling
        self._pending_objects: list[tuple[float, dict[str, Any]]] = []

    @property
    def remaining_budget(self) -> int:
        """Number of annotations still available."""
        return max(0, self.total_budget - self.used_budget)

    @property
    def is_exhausted(self) -> bool:
        """True if no budget remains."""
        return self.used_budget >= self.total_budget

    def should_annotate(
        self,
        uncertainty: ObjectUncertainty,
        object_data: dict[str, Any],
    ) -> bool:
        """Determine if this object should be annotated now.

        The decision depends on:
        1. Is there budget remaining?
        2. Does the strategy say to annotate this object?
        3. For uncertainty sampling, we may defer to batch selection
        """
        if self.is_exhausted:
            return False

        if self.strategy == AnnotationStrategy.CONFIDENCE_THRESHOLD:
            return uncertainty.should_request_annotation(self.uncertainty_threshold)

        elif self.strategy == AnnotationStrategy.UNCERTAINTY_SAMPLING:
            # Add to pending queue, will be selected in batch
            self._pending_objects.append((uncertainty.overall_uncertainty, object_data))
            # Immediately annotate if very uncertain
            if uncertainty.overall_uncertainty > 0.85:
                return True
            return False

        elif self.strategy == AnnotationStrategy.RANDOM_SAMPLING:
            # Random decision (but we'll control rate at higher level)
            return True

        elif self.strategy == AnnotationStrategy.DIVERSITY_SAMPLING:
            # Always add to pool, selection happens in batch
            self._pending_objects.append((uncertainty.overall_uncertainty, object_data))
            return False

        return False

    def select_batch(
        self,
        n: int | None = None,
    ) -> list[dict[str, Any]]:
        """Select N objects to annotate based on strategy.

        For uncertainty sampling: select highest uncertainty
        For diversity: cluster and select representatives
        """
        if n is None:
            n = self.remaining_budget

        n = min(n, self.remaining_budget)
        if n == 0 or not self._pending_objects:
            return []

        if self.strategy == AnnotationStrategy.UNCERTAINTY_SAMPLING:
            # Sort by uncertainty (highest first)
            sorted_pending = sorted(
                self._pending_objects,
                key=lambda x: x[0],
                reverse=True,
            )
            selected = sorted_pending[:n]
            self._pending_objects = sorted_pending[n:]
            return [obj for _, obj in selected]

        elif self.strategy == AnnotationStrategy.DIVERSITY_SAMPLING:
            # Simple diversity: spread across uncertainty ranges
            sorted_pending = sorted(
                self._pending_objects,
                key=lambda x: x[0],
                reverse=True,
            )
            # Select evenly across the range
            step = max(1, len(sorted_pending) // n)
            selected = sorted_pending[::step][:n]
            self._pending_objects = [obj for obj in sorted_pending if obj not in selected]
            return [obj for _, obj in selected]

        elif self.strategy == AnnotationStrategy.RANDOM_SAMPLING:
            import random

            selected = random.sample(self._pending_objects, min(n, len(self._pending_objects)))
            self._pending_objects = [obj for obj in self._pending_objects if obj not in selected]
            return [obj for _, obj in selected]

        return []

    def record_annotation(
        self,
        object_data: dict[str, Any],
        annotation_result: dict[str, Any],
    ) -> None:
        """Record that an annotation was used."""
        self.used_budget += 1
        self.annotated_objects.append(
            {
                "input": object_data,
                "result": annotation_result,
                "order": self.used_budget,
            }
        )

        logger.debug(f"Annotation used: {self.used_budget}/{self.total_budget} (class: {annotation_result.get('class_name', 'unknown')})")

    def get_efficiency_report(self) -> dict[str, Any]:
        """Generate report on annotation efficiency."""
        return {
            "total_budget": self.total_budget,
            "used_budget": self.used_budget,
            "remaining_budget": self.remaining_budget,
            "strategy": self.strategy.value,
            "annotations_by_class": self._count_by_class(),
        }

    def _count_by_class(self) -> dict[str, int]:
        """Count annotations by class."""
        counts: dict[str, int] = {}
        for ann in self.annotated_objects:
            class_name = ann["result"].get("class_name", "unknown")
            counts[class_name] = counts.get(class_name, 0) + 1
        return counts
