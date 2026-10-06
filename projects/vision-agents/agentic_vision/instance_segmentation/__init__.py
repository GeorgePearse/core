"""Instance segmentation programme and tools for agentic vision."""

from agentic_vision.instance_segmentation.programme import (
    InstanceSegmentationAnnotator,
    InstanceSegmentationSignature,
)
from agentic_vision.instance_segmentation.tools import (
    InstanceSegmentationToolkit,
    deduplicate_detections,
    parse_boxes_from_detections,
)
from agentic_vision.object_memory import ObjectMemoryBackgroundStore, ObjectMemoryRetriever

__all__ = [
    "InstanceSegmentationAnnotator",
    "InstanceSegmentationSignature",
    "InstanceSegmentationToolkit",
    "ObjectMemoryBackgroundStore",
    "ObjectMemoryRetriever",
    "deduplicate_detections",
    "parse_boxes_from_detections",
]
