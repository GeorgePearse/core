"""Agentic vision package: VLM clients that use code execution for Think-Act-Observe loops.

Includes active learning components for minimal-annotation instance segmentation.
"""

from agentic_vision.gemini_agentic_vision import (
    AgenticVisionResult,
    GeminiAgenticVisionClient,
)
from agentic_vision.object_memory import ObjectMemoryRetriever
from agentic_vision.instance_segmentation import (
    InstanceSegmentationAnnotator,
    InstanceSegmentationSignature,
    InstanceSegmentationToolkit,
    deduplicate_detections,
    parse_boxes_from_detections,
)
from agentic_vision.active_learning import (
    AnnotatedExample,
    AnnotationBudgetManager,
    AnnotationStrategy,
    KnowledgeBase,
    ObjectUncertainty,
)
from agentic_vision.coordinates import (
    BoxFormat,
    BoxValidationError,
    convert_box,
    validate_annotation_boxes,
    validate_box,
    validate_predictions_boxes,
)
from agentic_vision.active_learning_programme import (
    ActiveLearningResult,
    ActiveLearningSegmentationSignature,
    ActiveLearningSegmenter,
    SegmentationPrediction,
    run_active_learning_experiment,
)
from agentic_vision.experiment_runner import (
    ExperimentConfig,
    ExperimentResult,
    ExperimentRunner,
    GroundTruthSimulator,
    create_default_experiment_suite,
)
from agentic_vision.metrics import (
    SegmentationMetrics,
    aggregate_metrics,
    calculate_segmentation_metrics,
)
from agentic_vision.viewer_runtime import (
    AgenticVisionRunRecorder,
    get_viewer_artifact_path,
    list_viewer_runs,
    load_viewer_events,
    load_viewer_run,
)

__all__ = [
    # Core vision clients
    "AgenticVisionResult",
    "GeminiAgenticVisionClient",
    "ObjectMemoryRetriever",
    # Instance segmentation
    "InstanceSegmentationAnnotator",
    "InstanceSegmentationSignature",
    "InstanceSegmentationToolkit",
    "deduplicate_detections",
    "parse_boxes_from_detections",
    # Active learning
    "ActiveLearningSegmenter",
    "ActiveLearningResult",
    "ActiveLearningSegmentationSignature",
    "SegmentationPrediction",
    "AnnotationBudgetManager",
    "AnnotationStrategy",
    "KnowledgeBase",
    "ObjectUncertainty",
    "AnnotatedExample",
    # Coordinates
    "BoxFormat",
    "BoxValidationError",
    "convert_box",
    "validate_annotation_boxes",
    "validate_box",
    "validate_predictions_boxes",
    # Experiment framework
    "ExperimentRunner",
    "ExperimentConfig",
    "ExperimentResult",
    "GroundTruthSimulator",
    "create_default_experiment_suite",
    "run_active_learning_experiment",
    # Metrics
    "SegmentationMetrics",
    "aggregate_metrics",
    "calculate_segmentation_metrics",
    # Viewer runtime
    "AgenticVisionRunRecorder",
    "list_viewer_runs",
    "load_viewer_run",
    "load_viewer_events",
    "get_viewer_artifact_path",
]
