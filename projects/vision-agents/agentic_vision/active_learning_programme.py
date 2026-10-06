"""Active Learning Instance Segmentation Programme.

DSPy ReAct agent that performs instance segmentation while minimizing
human annotations through intelligent uncertainty-based sampling.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import dspy
from loguru import logger

from agentic_vision.active_learning import (
    AnnotatedExample,
    AnnotationBudgetManager,
    AnnotationStrategy,
    KnowledgeBase,
    ObjectUncertainty,
)
from agentic_vision.coordinates import BoxFormat, BoxValidationError, validate_box
from agentic_vision.instance_segmentation.tools import (
    InstanceSegmentationToolkit,
    parse_boxes_from_detections,
)


def get_image_log_reference(image: dspy.Image, max_length: int = 120) -> str:
    """Return a safe short image reference for logs."""
    url = getattr(image, "url", str(image))
    return url[:max_length]


@dataclass
class SegmentationPrediction:
    """A single segmentation prediction with uncertainty and provenance."""

    label: str
    box: tuple[float, float, float, float]  # x1, y1, x2, y2
    segmentation: list[tuple[float, float]] = field(default_factory=list)
    confidence: float = 0.5
    uncertainty: ObjectUncertainty = field(default_factory=ObjectUncertainty)

    # Provenance tracking
    detection_source: str = ""  # "qwen", "gemini", "human"
    classification_source: str = ""  # "qwen", "gemini", "knn", "human"
    segmentation_source: str = ""  # "sam3", "human"

    # Whether this was human-annotated
    is_human_annotated: bool = False
    human_annotation_cost: int = 0  # 1=label, 2=label+box, 3=full

    def to_annotation_format(self) -> str:
        """Convert to the standard annotation string format."""
        seg_str = ", ".join([f"{x:.0f}, {y:.0f}" for x, y in self.segmentation])
        return (
            f"object: {self.label} | "
            f"box: [{self.box[0]:.0f}, {self.box[1]:.0f}, {self.box[2]:.0f}, {self.box[3]:.0f}] | "
            f"segmentation: [{seg_str}] | "
            f"confidence={self.confidence:.2f}"
        )


@dataclass
class ActiveLearningResult:
    """Result of active learning segmentation including metrics and provenance."""

    predictions: list[SegmentationPrediction]
    annotations_used: int
    budget_remaining: int
    knowledge_base_state: dict[str, Any]
    processing_time_seconds: float

    # Performance metrics (if ground truth available)
    metrics: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "predictions": [
                {
                    "label": p.label,
                    "box": p.box,
                    "confidence": p.confidence,
                    "uncertainty": p.uncertainty.to_dict(),
                    "detection_source": p.detection_source,
                    "classification_source": p.classification_source,
                    "is_human_annotated": p.is_human_annotated,
                }
                for p in self.predictions
            ],
            "annotations_used": self.annotations_used,
            "budget_remaining": self.budget_remaining,
            "processing_time_seconds": self.processing_time_seconds,
            "metrics": self.metrics,
        }


class ActiveLearningSegmentationSignature(dspy.Signature):
    """Perform instance segmentation with active learning and minimal human input.

    Your goal is to generate accurate instance segmentations while using as few
    human annotations as possible. You have a limited budget of human interactions.

    AVAILABLE TOOLS:

    Detection & Segmentation:
    - locate_with_gemini: Find all objects with bounding boxes (no annotation cost)
    - classify_with_gemini: Assign labels to detected boxes (no annotation cost)
    - segment_with_sam3: Generate segmentation masks (no annotation cost)
    - verify_segmentation_with_gemini: Check segmentation quality (no annotation cost)
    - verify_segmentation_zoomed: Detailed zoom inspection of suspicious masks

    Knowledge & Learning:
    - query_object_memory_knn: Retrieve similar annotated examples from database
      Use this to bootstrap classification when similar objects exist in memory.

    Human Annotation (COSTLY - limited budget):
    - request_human_annotation: Ask human to annotate a specific object.
      This consumes 1 unit from your annotation budget. Use sparingly!
      Only request when:
      * Uncertainty is very high (>0.8)
      * No similar examples in object memory
      * Models disagree on classification
      * Segmentation verification fails

    Strategy:
    1. Detect all objects with locate_with_gemini
    2. For each detection:
       a. Query object memory KNN for similar examples
       b. If confident match exists, use that classification
       c. If uncertain, request_human_annotation (if budget allows)
       d. If no budget, use best-effort classification and flag as uncertain
    3. Generate segmentations with segment_with_sam3
    4. Verify quality and iterate on failures
    5. Record all human annotations to build knowledge for future images

    Remember: Your performance is measured by segmentation accuracy AND
    annotation efficiency. Using too many annotations reduces your score!
    """

    image: dspy.Image = dspy.InputField(desc="Image to segment with active learning")
    budget_remaining: int = dspy.InputField(
        desc="Number of human annotations still available"
    )
    prior_knowledge: str = dspy.InputField(
        desc="Summary of what we know from prior annotations (optional)"
    )

    segmentations: str = dspy.OutputField(
        desc="Instance segmentation results, one per line in standard format"
    )
    annotation_requests: str = dspy.OutputField(
        desc="List of object indices that need human annotation (comma-separated)"
    )
    uncertainty_summary: str = dspy.OutputField(
        desc="Summary of uncertainty levels for each detected object"
    )


class ActiveLearningSegmenter(dspy.Module):
    """Active learning-based instance segmentation agent.

    Uses DSPy ReAct to orchestrate detection, classification, and segmentation
    while intelligently selecting which objects need human annotation.

    Args:
        annotation_budget: Maximum number of human annotations allowed
        strategy: How to select objects for annotation
        uncertainty_threshold: Threshold above which to request annotation
        bootstrap_examples: Number of pre-loaded examples from database
        sam3_handler_name: SAM3 model to use for segmentation
    """

    def __init__(
        self,
        annotation_budget: int = 50,
        strategy: AnnotationStrategy = AnnotationStrategy.UNCERTAINTY_SAMPLING,
        uncertainty_threshold: float = 0.7,
        bootstrap_examples: int = 0,
        sam3_handler_name: str = "premier_sam3",
        dataset_name: str | None = None,
        enable_object_memory: bool = True,
    ) -> None:
        super().__init__()

        self.annotation_budget = annotation_budget
        self.strategy = strategy
        self.uncertainty_threshold = uncertainty_threshold
        self.sam3_handler_name = sam3_handler_name
        self.dataset_name = dataset_name
        self.enable_object_memory = enable_object_memory

        # Initialize budget manager and knowledge base
        self.budget_manager = AnnotationBudgetManager(
            total_budget=annotation_budget,
            strategy=strategy,
            uncertainty_threshold=uncertainty_threshold,
        )
        self.knowledge_base = KnowledgeBase(dataset_name)

        # Track state during processing
        self._toolkit: InstanceSegmentationToolkit | None = None
        self._human_input_fn: Callable[[str], str] | None = None

        # Bootstrap from database if requested
        self._bootstrap_knowledge = bootstrap_examples

        # Placeholder ReAct - replaced per forward() call
        self._init_react_agent()

    def _init_react_agent(self) -> None:
        """Initialize the ReAct agent with tool placeholders."""
        self.agent = dspy.ReAct(
            ActiveLearningSegmentationSignature,
            tools=[
                self._locate_with_gemini,
                self._classify_with_gemini,
                self._query_object_memory_knn,
                self._segment_with_sam3,
                self._verify_segmentation,
                self._verify_segmentation_zoomed,
                self._request_human_annotation,
            ],
            max_iters=15,
        )

    def _locate_with_gemini(self, prompt: str) -> str:
        """Locate objects using Gemini."""
        if self._toolkit is None:
            return "Error: Toolkit not initialized"
        return self._toolkit.locate_with_gemini(prompt)

    def _classify_with_gemini(self, detections: str) -> str:
        """Classify detected objects using Gemini."""
        if self._toolkit is None:
            return "Error: Toolkit not initialized"
        return self._toolkit.classify_with_gemini(detections)

    def _query_object_memory_knn(
        self,
        annotation_id: int,
        max_neighbors: int = 5,
    ) -> str:
        """Query object memory for similar examples."""
        neighbors = self.knowledge_base.query_similar(annotation_id, max_neighbors)
        if not neighbors:
            return "No similar examples found in object memory."

        # Format as readable summary
        lines = [f"Found {len(neighbors)} similar examples:"]
        for n in neighbors[:3]:  # Show top 3
            lines.append(
                f"- {n.get('class_name', 'unknown')} (distance={n.get('distance', 0):.2f}, proximity={n.get('proximity_score', 0):.2f})"
            )
        return "\n".join(lines)

    def _segment_with_sam3(self, detections: str) -> str:
        """Generate segmentations using SAM3."""
        if self._toolkit is None:
            return "Error: Toolkit not initialized"
        return self._toolkit.segment_with_sam3(detections)

    def _verify_segmentation(
        self, segmentations: str, overlay_opacity: float = 0.35
    ) -> str:
        """Verify segmentation quality."""
        if self._toolkit is None:
            return "Error: Toolkit not initialized"
        return self._toolkit.verify_segmentation_with_gemini(
            segmentations, overlay_opacity
        )

    def _verify_segmentation_zoomed(
        self,
        segmentations: str,
        target_index: int,
        zoom_factor: float = 2.0,
        center_x_offset: float = 0.0,
        center_y_offset: float = 0.0,
    ) -> str:
        """Detailed zoom verification of one segmentation."""
        if self._toolkit is None:
            return "Error: Toolkit not initialized"
        return self._toolkit.verify_segmentation_zoomed(
            segmentations=segmentations,
            target_index=target_index,
            zoom_factor=zoom_factor,
            center_x_offset=center_x_offset,
            center_y_offset=center_y_offset,
        )

    def _request_human_annotation(
        self,
        object_description: str,
        current_guess: str,
        uncertainty_reasons: str,
    ) -> str:
        """Request human annotation for an uncertain object.

        This consumes budget! Only call when necessary.
        """
        if self.budget_manager.is_exhausted:
            return "ANNOTATION DENIED: Budget exhausted. Proceed with best-effort prediction."

        if self._human_input_fn is None:
            # Auto-simulate without human (for experiments)
            return (
                f"SIMULATED ANNOTATION: Would ask human about '{object_description}'. "
                f"Current guess: {current_guess}. "
                f"Uncertain because: {uncertainty_reasons}"
            )

        # Build question for human
        question = (
            f"I need help classifying an object.\n\n"
            f"Description: {object_description}\n"
            f"My current guess: {current_guess}\n"
            f"I'm uncertain because: {uncertainty_reasons}\n\n"
            f"Please provide the correct class name, or say 'skip' to ignore."
        )

        try:
            answer = self._human_input_fn(question)

            # Record the annotation
            self.budget_manager.record_annotation(
                object_data={"description": object_description, "guess": current_guess},
                annotation_result={"class_name": answer, "source": "human"},
            )

            # Add to knowledge base
            example = AnnotatedExample(
                class_name=answer,
                source="human",
            )
            self.knowledge_base.add_example(example)

            return f"HUMAN ANNOTATION: {answer}"

        except Exception as exc:
            logger.warning(f"Human annotation failed: {exc}")
            return f"ANNOTATION FAILED: {exc}. Using best guess: {current_guess}"

    def forward(
        self,
        image: dspy.Image,
        frame_uri: str | None = None,
        human_input_fn: Callable[[str], str] | None = None,
    ) -> ActiveLearningResult:
        """Process an image with active learning.

        Args:
            image: DSPy Image to segment
            frame_uri: GCS URI for SAM3 segmentation
            human_input_fn: Callback for human-in-the-loop, or None for simulation

        Returns:
            ActiveLearningResult with predictions and provenance
        """
        t0 = time.monotonic()
        image_ref = get_image_log_reference(image)

        logger.info(
            f"ActiveLearningSegmenter | image={image_ref} "
            f"budget={self.budget_manager.remaining_budget}/{self.annotation_budget} "
            f"strategy={self.strategy.value}"
        )

        # Initialize toolkit
        self._toolkit = InstanceSegmentationToolkit(
            image=image,
            frame_uri=frame_uri,
            dataset_name=self.dataset_name,
            sam3_handler_name=self.sam3_handler_name,
            human_input_fn=human_input_fn,
            enable_object_memory=self.enable_object_memory,
        )
        self._human_input_fn = human_input_fn

        try:
            # Step 1: Detect all objects
            detections_text = self._toolkit.locate_with_gemini(
                "Find all objects in this image"
            )
            parsed_detections = parse_boxes_from_detections(detections_text)

            logger.info(f"Detected {len(parsed_detections)} objects")

            # Step 2: Classify with uncertainty estimation
            predictions: list[SegmentationPrediction] = []

            for idx, (label, x1, y1, x2, y2, conf) in enumerate(parsed_detections):
                box = (x1, y1, x2, y2)
                try:
                    validate_box(
                        box,
                        BoxFormat.XYXY_NORM_1K,
                        context=f"detection[{idx}] '{label}'",
                    )
                except BoxValidationError as exc:
                    logger.warning(f"Skipping invalid detection: {exc}")
                    continue

                # Estimate uncertainty using knowledge base
                uncertainty = self.knowledge_base.estimate_uncertainty_for_detection(
                    box=(x1, y1, x2, y2),
                    label=label,
                )
                uncertainty.detection_confidence = conf

                # Check if we should request human annotation
                object_data = {
                    "index": idx,
                    "label": label,
                    "box": (x1, y1, x2, y2),
                    "uncertainty": uncertainty.overall_uncertainty,
                }

                should_annotate = self.budget_manager.should_annotate(
                    uncertainty=uncertainty,
                    object_data=object_data,
                )

                pred = SegmentationPrediction(
                    label=label,
                    box=(x1, y1, x2, y2),
                    confidence=conf,
                    uncertainty=uncertainty,
                    detection_source="qwen",
                    classification_source="gemini"
                    if not should_annotate
                    else "pending_human",
                )

                if should_annotate and not self.budget_manager.is_exhausted:
                    # Will request human annotation
                    pred.classification_source = "human"
                    pred.is_human_annotated = True
                    pred.human_annotation_cost = 1

                predictions.append(pred)

            # Step 3: Select batch and request annotations
            batch = self.budget_manager.select_batch()
            for obj_data in batch:
                idx = obj_data["index"]
                pred = predictions[idx]

                # Request human annotation (or simulate)
                result = self._request_human_annotation(
                    object_description=f"Object {idx}: {pred.label} at box {pred.box}",
                    current_guess=pred.label,
                    uncertainty_reasons="; ".join(pred.uncertainty.uncertainty_reasons),
                )

                # Update prediction with result
                if "HUMAN ANNOTATION:" in result:
                    # Extract the human-provided label
                    human_label = result.split("HUMAN ANNOTATION:")[1].strip()
                    pred.label = human_label
                    pred.confidence = 0.95  # High confidence after human input

                logger.info(
                    f"Annotated object {idx}: {pred.label} (budget remaining: {self.budget_manager.remaining_budget})"
                )

            # Step 4: Generate segmentations
            detection_text = "\n".join(
                [
                    f"object: {p.label} | box: [{p.box[0]:.0f}, {p.box[1]:.0f}, {p.box[2]:.0f}, {p.box[3]:.0f}] | confidence={p.confidence:.2f}"
                    for p in predictions
                ]
            )

            if frame_uri:
                segmentations_text = self._toolkit.segment_with_sam3(detection_text)

                # Parse segmentations and update predictions
                # (Simplified - in real implementation would parse properly)
                for pred in predictions:
                    pred.segmentation_source = "sam3"

            elapsed = time.monotonic() - t0

            # Build result
            result = ActiveLearningResult(
                predictions=predictions,
                annotations_used=self.budget_manager.used_budget,
                budget_remaining=self.budget_manager.remaining_budget,
                knowledge_base_state=self.knowledge_base.to_dict(),
                processing_time_seconds=elapsed,
            )

            logger.info(
                f"ActiveLearning complete: {len(predictions)} predictions, {result.annotations_used} annotations used, {elapsed:.1f}s"
            )

            return result

        finally:
            self._toolkit = None
            self._human_input_fn = None

    def bootstrap_from_database(
        self,
        n_examples: int,
        strategy: str = "diverse",
    ) -> int:
        """Load N examples from database to bootstrap knowledge.

        Returns:
            Number of examples loaded
        """
        if not self.dataset_name:
            logger.warning("Cannot bootstrap: no dataset_name provided")
            return 0

        # This would query the actual database in production
        # For now, simulate with empty knowledge base
        logger.info(f"Bootstrapping with {n_examples} examples (strategy: {strategy})")

        # In real implementation:
        # examples = query_database_for_examples(self.dataset_name, n_examples, strategy)
        # for ex in examples:
        #     self.knowledge_base.add_example(ex)

        return 0  # Placeholder


# Convenience function for experiments
def run_active_learning_experiment(
    images: list[dspy.Image],
    ground_truths: list[list[dict]] | None = None,
    annotation_budgets: list[int] = [0, 5, 10, 20, 50],
    strategies: list[AnnotationStrategy] = [AnnotationStrategy.UNCERTAINTY_SAMPLING],
    dataset_name: str | None = None,
) -> dict[str, list[tuple[int, float]]]:
    """Run active learning experiments across multiple configurations.

    Args:
        images: List of images to process
        ground_truths: Optional ground truth annotations for metrics
        annotation_budgets: List of budget levels to test
        strategies: List of strategies to compare
        dataset_name: Dataset name for KNN queries

    Returns:
        Dict mapping strategy names to list of (annotations, performance) tuples
    """
    results: dict[str, list[tuple[int, float]]] = {}

    for strategy in strategies:
        strategy_results: list[tuple[int, float]] = []

        for budget in annotation_budgets:
            segmenter = ActiveLearningSegmenter(
                annotation_budget=budget,
                strategy=strategy,
                dataset_name=dataset_name,
            )

            total_annotations = 0
            total_score = 0.0

            for idx, image in enumerate(images):
                result = segmenter(image)
                total_annotations += result.annotations_used

                # Calculate score (would use ground truth if available)
                if ground_truths and idx < len(ground_truths):
                    score = _calculate_iou_score(result.predictions, ground_truths[idx])
                else:
                    score = _estimate_score_from_confidence(result.predictions)

                total_score += score

            avg_score = total_score / len(images) if images else 0.0
            strategy_results.append((total_annotations, avg_score))

        results[strategy.value] = strategy_results

    return results


def _calculate_iou_score(
    predictions: list[SegmentationPrediction],
    ground_truth: list[dict],
) -> float:
    """Calculate mean IoU against ground truth."""
    # Simplified - real implementation would compute proper IoU
    if not predictions:
        return 0.0

    # Placeholder: average confidence as proxy
    return sum(p.confidence for p in predictions) / len(predictions)


def _estimate_score_from_confidence(
    predictions: list[SegmentationPrediction],
) -> float:
    """Estimate performance score from prediction confidences."""
    if not predictions:
        return 0.0
    return sum(p.confidence for p in predictions) / len(predictions)
