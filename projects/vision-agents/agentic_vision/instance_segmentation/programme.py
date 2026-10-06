"""Instance segmentation annotation programme using DSPy ReAct with multi-model tools.

Orchestrates Gemini and SAM3 through a ReAct agent that learns
optimal tool-calling strategies via DSPy optimization.
"""

from __future__ import annotations

import time
from collections.abc import Callable

import dspy
from loguru import logger

from agentic_vision.instance_segmentation.tools import (
    InstanceSegmentationToolkit,
)
from agentic_vision.tracing_react import TracingReAct
from agentic_vision.viewer_runtime import AgenticVisionRunRecorder


def get_image_log_reference(image: dspy.Image, max_length: int = 120) -> str:
    """Return a safe short image reference for logs."""
    url = getattr(image, "url", str(image))
    return url[:max_length]


class InstanceSegmentationSignature(dspy.Signature):
    """Produce instance segmentation annotations for all objects in the image.

    You have access to specialized tools:
    - locate_with_gemini: Find all objects with precise bounding boxes
    - classify_with_gemini: Assign specific labels to detected boxes (best at visual classification)
    - filter_detections_by_camera_mask: Remove detections outside the configured belt region
    - segment_with_sam3: PRIMARY iterative tool call for mask generation/refinement
      with positive/negative points, positive/negative prompt notes, and class-name experiments
    - plan_mask_refinement_with_gemini: Ask Gemini to choose keep/grabcut/superpixel_snap/cleanup
      and propose positive/negative refinement points for one suspicious mask
    - refine_mask_with_cv2: Deterministic CV refinement for one target mask using
      GrabCut, superpixel snapping, or cleanup
    - verify_segmentation_with_gemini: Render masks on image and check quality with Gemini
    - verify_segmentation_zoomed: ZOOMED-IN verification of ONE segmentation at high resolution
      (use this for boundary detail critique — e.g., upper-right quadrant of bbox)
    - find_missed_objects_with_gemini: Check clean image for objects not yet detected
    - retrieve_similar_annotations_knn: Fetch nearest annotation instances + metadata via TurboPuffer
    - remember_background_objects: Store background detections using DINOv2 embeddings (TurboPuffer/Qdrant)
    - zoom_in: Focus all tools on a specific region at higher resolution
    - reset_to_full_image: Return to the full image after inspecting a region
    - execute_code: Run a Python snippet for custom image processing or analysis
    - ask_for_input: Ask a human operator when confidence is low

    Recommended workflow:
    1. locate_with_gemini to find all objects with tight bounding boxes.
    2. classify_with_gemini with the detection output to get specific category labels.
    3. filter_detections_by_camera_mask with the camera_id before segmentation.
    4. segment_with_sam3 with the filtered detections to get segmentation masks.
    5. Re-run segment_with_sam3 frequently as the primary loop with:
       - positive_points / negative_points JSON keyed by detection index
       - positive_prompt / negative_prompt experiments
       - class_rename_rules string experiments
    6. For suspicious masks, use plan_mask_refinement_with_gemini to choose between
       keep / grabcut / superpixel_snap / cleanup and propose refinement points.
    7. Run refine_mask_with_cv2 on the suspicious mask. Prefer repeated SAM3 calls first;
       use CV refinement when SAM3 still leaks, leaves holes, or needs local boundary snapping.
    8. Immediately verify every refined mask with verify_segmentation_with_gemini or
       verify_segmentation_zoomed before accepting it.
    9. For any suspicious segmentations, use verify_segmentation_zoomed with modes like:
       - "upper_right_quadrant" to check top-right boundary details
       - "bbox_with_padding" to see full object context at higher zoom
    10. find_missed_objects_with_gemini to catch anything overlooked.
    11. If new objects found, segment them with segment_with_sam3.
    12. Optionally retrieve_similar_annotations_knn for object-level nearest-neighbor context.
    13. If detections are known background clutter, call remember_background_objects.
    14. For dense regions: zoom_in, then re-run locate/classify/segment/verify/find_missed
        on the crop — coordinates are automatically remapped. Call reset_to_full_image when done.

    Output one annotation per line:
    object: <label> | box: [x1, y1, x2, y2] | segmentation: [x0, y0, ...] | confidence=0.XX
    """

    image: dspy.Image = dspy.InputField(
        desc="Image to annotate with instance segmentations"
    )
    annotations: str = dspy.OutputField(
        desc=(
            "Instance segmentation annotations, one per line. "
            "Format: object: <label> | box: [x1, y1, x2, y2] | segmentation: [x0, y0, ...] | confidence=0.XX"
        )
    )


class InstanceSegmentationAnnotator(dspy.Module):
    """ReAct-based instance segmentation annotator.

    Uses Gemini for detection and SAM3 for segmentation masks.
    The ReAct agent learns the optimal tool-calling strategy through DSPy optimization.
    """

    def __init__(
        self,
        max_iters: int = 12,
        dataset_name: str | None = None,
        sam3_handler_name: str = "premier_sam3",
    ) -> None:
        super().__init__()
        self._dataset_name = dataset_name
        self._sam3_handler_name = sam3_handler_name
        self._max_iters = max_iters
        self._toolkit: InstanceSegmentationToolkit | None = None

        # Placeholder tools for ReAct initialization — replaced per-forward call
        self.annotator = TracingReAct(
            InstanceSegmentationSignature,
            tools=[
                self._locate_with_gemini,
                self._classify_with_gemini,
                self._filter_detections_by_camera_mask,
                self._segment_with_sam3,
                self._plan_mask_refinement_with_gemini,
                self._refine_mask_with_cv2,
                self._verify_segmentation_with_gemini,
                self._verify_segmentation_zoomed,
                self._find_missed_objects_with_gemini,
                self._retrieve_similar_annotations_knn,
                self._remember_background_objects,
                self._zoom_in,
                self._reset_to_full_image,
                self._execute_code,
                self._ask_for_input,
            ],
            max_iters=max_iters,
        )

    def _locate_with_gemini(self, prompt: str) -> str:
        """Locate all objects with precise bounding boxes using Gemini."""
        if self._toolkit is None:
            raise RuntimeError("Toolkit not initialized; call forward() first")
        return self._toolkit.locate_with_gemini(prompt)

    def _classify_with_gemini(self, detections: str) -> str:
        """Classify detected objects with specific labels using Gemini."""
        if self._toolkit is None:
            raise RuntimeError("Toolkit not initialized; call forward() first")
        return self._toolkit.classify_with_gemini(detections)

    def _filter_detections_by_camera_mask(self, detections: str, camera_id: int) -> str:
        """Filter detections against configured masks for a camera."""
        if self._toolkit is None:
            raise RuntimeError("Toolkit not initialized; call forward() first")
        return self._toolkit.filter_detections_by_camera_mask(
            detections=detections, camera_id=camera_id
        )

    def _segment_with_sam3(
        self,
        detections: str,
        positive_points: str = "",
        negative_points: str = "",
        positive_prompt: str = "",
        negative_prompt: str = "",
        class_rename_rules: str = "",
    ) -> str:
        """Generate segmentation masks for detected boxes using SAM3."""
        if self._toolkit is None:
            raise RuntimeError("Toolkit not initialized; call forward() first")
        return self._toolkit.segment_with_sam3(
            detections=detections,
            positive_points=positive_points,
            negative_points=negative_points,
            positive_prompt=positive_prompt,
            negative_prompt=negative_prompt,
            class_rename_rules=class_rename_rules,
        )

    def _verify_segmentation_with_gemini(
        self, segmentations: str, overlay_opacity: float = 0.35
    ) -> str:
        """Verify segmentation mask quality by rendering masks on image and asking Gemini."""
        if self._toolkit is None:
            raise RuntimeError("Toolkit not initialized; call forward() first")
        return self._toolkit.verify_segmentation_with_gemini(
            segmentations, overlay_opacity
        )

    def _plan_mask_refinement_with_gemini(
        self,
        segmentations: str,
        target_index: int,
        zoom_factor: float = 2.0,
        overlay_opacity: float = 0.45,
        default_operator: str = "grabcut",
    ) -> str:
        """Ask Gemini to choose the next deterministic refinement operator for one mask."""
        if self._toolkit is None:
            raise RuntimeError("Toolkit not initialized; call forward() first")
        return self._toolkit.plan_mask_refinement_with_gemini(
            segmentations=segmentations,
            target_index=target_index,
            zoom_factor=zoom_factor,
            overlay_opacity=overlay_opacity,
            default_operator=default_operator,
        )

    def _refine_mask_with_cv2(
        self,
        segmentations: str,
        target_index: int,
        mode: str = "auto",
        refinement_plan: str = "",
        positive_points: str = "",
        negative_points: str = "",
        iterations: int | None = None,
        superpixel_segments: int | None = None,
        cleanup_kernel_size: int | None = None,
        padding_percent: float | None = None,
    ) -> str:
        """Refine one mask with GrabCut, superpixel snapping, or cleanup."""
        if self._toolkit is None:
            raise RuntimeError("Toolkit not initialized; call forward() first")
        return self._toolkit.refine_mask_with_cv2(
            segmentations=segmentations,
            target_index=target_index,
            mode=mode,
            refinement_plan=refinement_plan,
            positive_points=positive_points,
            negative_points=negative_points,
            iterations=iterations,
            superpixel_segments=superpixel_segments,
            cleanup_kernel_size=cleanup_kernel_size,
            padding_percent=padding_percent,
        )

    def _verify_segmentation_zoomed(
        self,
        segmentations: str,
        target_index: int,
        zoom_factor: float = 2.0,
        center_x_offset: float = 0.0,
        center_y_offset: float = 0.0,
        min_context_percent: float = 15.0,
        overlay_opacity: float = 0.45,
    ) -> str:
        """Verify ONE segmentation at zoomed-in resolution for detailed boundary critique.

        Use this when verify_segmentation_with_gemini flags a suspicious mask and you
        want to examine boundary details at higher resolution.

        Args:
            segmentations: Full segmentation output from segment_with_sam3.
            target_index: Index of the segmentation to verify in detail.
            zoom_factor: How much to zoom in (1.0 = bbox size, 2.0 = 2x zoom, 4.0 = 4x zoom).
            center_x_offset: Horizontal offset from bbox center as % of bbox width.
                -50 = left edge, 0 = center, 50 = right edge.
            center_y_offset: Vertical offset from bbox center as % of bbox height.
                -50 = top edge, 0 = center, 50 = bottom edge.
            min_context_percent: Minimum % of bbox to include even at high zoom.
            overlay_opacity: Mask transparency (default 0.45 for zoomed views).
        """
        if self._toolkit is None:
            raise RuntimeError("Toolkit not initialized; call forward() first")
        return self._toolkit.verify_segmentation_zoomed(
            segmentations=segmentations,
            target_index=target_index,
            zoom_factor=zoom_factor,
            center_x_offset=center_x_offset,
            center_y_offset=center_y_offset,
            min_context_percent=min_context_percent,
            overlay_opacity=overlay_opacity,
        )

    def _find_missed_objects_with_gemini(self, existing_detections: str) -> str:
        """Check the clean original image for objects missed by prior steps."""
        if self._toolkit is None:
            raise RuntimeError("Toolkit not initialized; call forward() first")
        return self._toolkit.find_missed_objects_with_gemini(existing_detections)

    def _retrieve_similar_annotations_knn(
        self, annotation_id: int, max_neighbors: int = 5
    ) -> str:
        """Retrieve KNN-similar annotations with metadata."""
        if self._toolkit is None:
            raise RuntimeError("Toolkit not initialized; call forward() first")
        return self._toolkit.retrieve_similar_annotations_knn(
            annotation_id=annotation_id, max_neighbors=max_neighbors
        )

    def _remember_background_objects(
        self,
        detections: str,
        camera_id: int | None = None,
        reason: str = "background_object",
    ) -> str:
        """Store likely background detections into object memory."""
        if self._toolkit is None:
            raise RuntimeError("Toolkit not initialized; call forward() first")
        return self._toolkit.remember_background_objects(
            detections=detections, camera_id=camera_id, reason=reason
        )

    def _zoom_in(self, x1: int, y1: int, x2: int, y2: int) -> str:
        """Zoom into a region — all subsequent tools operate on this crop."""
        if self._toolkit is None:
            raise RuntimeError("Toolkit not initialized; call forward() first")
        return self._toolkit.zoom_in(x1, y1, x2, y2)

    def _reset_to_full_image(self) -> str:
        """Reset to full image after inspecting a cropped region."""
        if self._toolkit is None:
            raise RuntimeError("Toolkit not initialized; call forward() first")
        return self._toolkit.reset_to_full_image()

    def _execute_code(self, code: str) -> str:
        """Execute a Python snippet with access to the image."""
        if self._toolkit is None:
            raise RuntimeError("Toolkit not initialized; call forward() first")
        return self._toolkit.execute_code(code)

    def _ask_for_input(self, question: str) -> str:
        """Ask a human operator for guidance when confidence is low."""
        if self._toolkit is None:
            raise RuntimeError("Toolkit not initialized; call forward() first")
        return self._toolkit.ask_for_input(question)

    def forward(
        self,
        image: dspy.Image,
        frame_uri: str | None = None,
        human_input_fn: Callable[[str], str] | None = None,
        viewer_recorder: AgenticVisionRunRecorder | None = None,
    ) -> dspy.Prediction:
        """Run the instance segmentation annotation pipeline.

        Args:
            image: DSPy Image to annotate.
            frame_uri: GCS URI for SAM3 segmentation (optional but needed for masks).
            human_input_fn: Optional callback ``fn(question: str) -> str`` that the
                agent can call when it needs human guidance. If None, the agent
                proceeds autonomously. Wire this to a chatbot, Slack thread, or
                interactive UI for human-in-the-loop annotation.

        Returns:
            Prediction with annotations field containing instance segmentations.
        """
        image_ref = get_image_log_reference(image, max_length=120)
        logger.debug(
            f"InstanceSegmentationAnnotator.forward | image={image_ref} "
            f"frame_uri={'yes' if frame_uri else 'no'} "
            f"dataset={self._dataset_name or 'none'} "
            f"human_input={'available' if human_input_fn else 'unavailable'}"
        )

        self._toolkit = InstanceSegmentationToolkit(
            image=image,
            frame_uri=frame_uri,
            dataset_name=self._dataset_name,
            sam3_handler_name=self._sam3_handler_name,
            human_input_fn=human_input_fn,
            viewer_recorder=viewer_recorder,
        )

        try:
            if viewer_recorder is not None:
                viewer_recorder.emit_event(
                    "frame_started",
                    status="running",
                    message="Started instance-segmentation run",
                    payload={
                        "frame_uri": frame_uri,
                        "dataset_name": self._dataset_name,
                        "sam3_handler_name": self._sam3_handler_name,
                        "max_iters": self._max_iters,
                    },
                )
            t0 = time.monotonic()
            prediction = self.annotator(image=image, viewer_recorder=viewer_recorder)
            elapsed = time.monotonic() - t0

            annotation_count = sum(
                1
                for line in prediction.annotations.strip().splitlines()
                if line.strip() and "no objects" not in line.lower()
            )
            logger.debug(
                f"InstanceSegmentationAnnotator complete ({elapsed:.1f}s): {annotation_count} annotations"
            )
            if viewer_recorder is not None:
                viewer_recorder.emit_event(
                    "frame_completed",
                    status="ok",
                    message="Completed instance-segmentation run",
                    payload={
                        "annotation_count": annotation_count,
                        "elapsed_seconds": round(elapsed, 3),
                        "annotations_preview": prediction.annotations[:1200],
                    },
                )
                viewer_recorder.update_status(
                    "completed", result_annotations=prediction.annotations
                )
                viewer_recorder.emit_event(
                    "run_completed",
                    status="ok",
                    message="Run completed",
                    payload={
                        "annotation_count": annotation_count,
                        "elapsed_seconds": round(elapsed, 3),
                    },
                )

            return dspy.Prediction(
                annotations=prediction.annotations,
            )
        except Exception as exc:
            if viewer_recorder is not None:
                viewer_recorder.update_status("failed", error=str(exc))
                viewer_recorder.emit_event(
                    "run_failed",
                    status="error",
                    message="Run failed",
                    payload={"error": str(exc)},
                )
            raise
        finally:
            self._toolkit = None
