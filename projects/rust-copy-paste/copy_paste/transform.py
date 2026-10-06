"""Albumentations-compatible copy-paste augmentation using Rust implementation."""

from typing import Any, Dict, Optional

import albumentations as A  # type: ignore[import-untyped]
import numpy as np
from loguru import logger

try:
    from copy_paste._core import CopyPasteTransform  # type: ignore[import-untyped]

    RUST_AVAILABLE = True
except ImportError:
    logger.warning("copy_paste Rust module not available. Build with: maturin develop")
    RUST_AVAILABLE = False


class CopyPasteAugmentation(A.DualTransform):
    """Copy-paste augmentation using Rust implementation with Albumentations interface.

    This transform applies copy-paste augmentation to images and masks, utilizing
    a Rust implementation for high performance. It maintains full compatibility with
    Albumentations' DualTransform interface.

    Args:
        image_width: Width of output images (default: 512)
        image_height: Height of output images (default: 512)
        max_paste_objects: Maximum number of objects to paste per image (default: 1)
        use_rotation: Whether to apply random rotation (default: True)
        use_scaling: Whether to apply random scaling (default: True)
        rotation_range: Range of rotation in degrees (min, max). Default: (-30.0, 30.0)
        scale_range: Range of scaling factors (min, max). Default: (0.8, 1.2)
        use_random_background: Whether to generate random background (default: False)
        blend_mode: Blending mode ('normal' or 'xray'). Default: 'normal'
        object_counts: Dictionary mapping class names (str) to exact count of objects
                      to paste per class. Example: {'person': 2, 'car': 1}
                      (default: {})
        p: Probability of applying the transform (0.0 to 1.0) (default: 1.0)

    Example:
        >>> transform = CopyPasteAugmentation(
        ...     image_width=512,
        ...     image_height=512,
        ...     object_counts={'person': 2, 'car': 1},
        ...     use_rotation=True,
        ...     use_scaling=True
        ... )
        >>> augmented = transform(image=img, mask=mask)
    """

    def __init__(
        self,
        image_width: int = 512,
        image_height: int = 512,
        max_paste_objects: int = 1,
        use_rotation: bool = True,
        use_scaling: bool = True,
        rotation_range: tuple[float, float] = (-30.0, 30.0),
        scale_range: tuple[float, float] = (0.8, 1.2),
        use_random_background: bool = False,
        blend_mode: str = "normal",
        object_counts: Optional[Dict[str, int]] = None,
        p: float = 1.0,
    ):
        """Initialize the CopyPasteAugmentation transform.

        Args:
            object_counts: Optional dict mapping class names (str) to exact number of objects
                          to paste per class. Example: {'person': 2, 'car': 1}
                          If None, no per-class count constraint is applied.
        """
        super().__init__(p=p)

        if not RUST_AVAILABLE:
            raise RuntimeError(
                "Rust implementation not available. "
                "Build with: pip install -e . or maturin develop"
            )

        # Validate input dimensions
        if image_width <= 0 or image_height <= 0:
            raise ValueError(
                f"image_width ({image_width}) and image_height ({image_height}) must be positive integers"
            )

        # Validate object_counts
        if object_counts:
            for class_name, count in object_counts.items():
                if not isinstance(count, (int, float)) or count < 0:
                    raise ValueError(
                        f"object_counts['{class_name}'] must be non-negative number, got {count}"
                    )

        self.image_width = image_width
        self.image_height = image_height
        self.max_paste_objects = max_paste_objects
        self.use_rotation = use_rotation
        self.use_scaling = use_scaling
        self.rotation_range = rotation_range
        self.scale_range = scale_range
        self.use_random_background = use_random_background
        self.blend_mode = blend_mode
        self.object_counts = object_counts or {}
        self._last_mask_output: Optional[np.ndarray] = None
        self._cached_source_mask: Optional[np.ndarray] = None

        # Initialize Rust transform
        self.rust_transform = CopyPasteTransform(
            image_width=image_width,
            image_height=image_height,
            max_paste_objects=max_paste_objects,
            use_rotation=use_rotation,
            use_scaling=use_scaling,
            use_random_background=use_random_background,
            blend_mode=blend_mode,
            object_counts=self.object_counts if self.object_counts else None,
            rotation_range=rotation_range,
            scale_range=scale_range,
        )

        logger.info(
            f"Initialized CopyPasteAugmentation | "
            f"size=({image_width}x{image_height}), "
            f"max_objects={max_paste_objects}, "
            f"rotation={use_rotation}, scaling={use_scaling}"
        )

    def __call__(self, force: bool = False, **kwargs: Any) -> dict[str, Any]:
        """Override Albumentations __call__ to handle image+mask together.

        Copy-paste augmentation needs both image and mask simultaneously to
        extract objects, but Albumentations DualTransform calls apply() and
        apply_to_mask() separately. This override processes them together.
        """
        if "image" not in kwargs:
            raise ValueError("image is required")

        # Cache the mask for use in apply()
        if "mask" in kwargs:
            self._cached_source_mask = kwargs["mask"]

        try:
            # Call parent __call__ which will invoke apply() and apply_to_mask()
            result = super().__call__(force=force, **kwargs)
            return result
        finally:
            # Always clear cache, even if an exception occurs
            self._cached_source_mask = None
            self._last_mask_output = None

    def apply(
        self,
        img: np.ndarray,
        **params: Any,
    ) -> np.ndarray:
        """Apply copy-paste augmentation to image.

        Args:
            img: Input image as numpy array (H, W, C) in BGR format

        Returns:
            Augmented image
        """
        logger.debug(
            f"apply() called with image shape {img.shape}, params keys: {list(params.keys())}"
        )
        # Convert to uint8 if needed
        if img.dtype != np.uint8:
            img = (
                (img * 255).astype(np.uint8)
                if img.max() <= 1.0
                else img.astype(np.uint8)
            )

        # Ensure image is BGR
        if img.ndim != 3 or img.shape[2] != 3:
            raise ValueError(f"Expected BGR image (H, W, 3), got shape {img.shape}")

        # Call Rust implementation
        try:
            # Use cached mask (set in __call__) or fallback to params
            source_mask = self._prepare_mask(
                self._cached_source_mask
                if self._cached_source_mask is not None
                else params.get("mask"),
                img.shape[0],
                img.shape[1],
            )
            target_mask = self._prepare_mask(
                params.get("target_mask"), img.shape[0], img.shape[1]
            )

            augmented_image, augmented_mask = self.rust_transform.apply(
                np.ascontiguousarray(img),
                source_mask,
                target_mask,
            )
            self._last_mask_output = self._normalize_mask_output(
                augmented_mask, params.get("mask")
            )
            return augmented_image
        except ValueError as e:
            # Expected errors from validation (bad input format, dimension mismatches)
            logger.warning(f"Augmentation skipped due to invalid input: {e}")
            self._last_mask_output = None
            return img
        except RuntimeError as e:
            # Rust implementation errors (memory issues, processing failures)
            logger.error(f"Rust augmentation failed: {e}", exc_info=True)
            self._last_mask_output = None
            raise
        except Exception as e:
            # Unexpected errors - log with full traceback and re-raise
            logger.error(f"Unexpected error in augmentation: {e}", exc_info=True)
            self._last_mask_output = None
            raise

    def apply_to_masks(
        self,
        masks: list[np.ndarray],
        **params: Any,
    ) -> list[np.ndarray]:
        """Apply transformations to masks.

        Args:
            masks: List of binary masks (each H x W)

        Returns:
            Transformed masks
        """
        # Masks are typically modified during copy-paste to reflect new object positions
        # For now, return unchanged as the Rust implementation needs full algorithm
        # In production: convert masks to Rust format, apply transformations, convert back
        if not masks:
            return masks

        return [self.apply_to_mask(mask, **params) for mask in masks]

    def apply_to_mask(
        self,
        mask: np.ndarray,
        **params: Any,
    ) -> np.ndarray:
        """Return mask output from Rust if available, otherwise sanitize input mask."""
        mask = self._ensure_uint8(mask)

        if mask.ndim != 2:
            raise ValueError(f"Expected 2D mask, got shape {mask.shape}")

        if self._last_mask_output is not None:
            target_shape = (int(mask.shape[0]), int(mask.shape[1]))
            output = self._resize_mask_if_needed(self._last_mask_output, target_shape)
            self._last_mask_output = None
            return output

        return mask

    def apply_to_bboxes(
        self,
        bboxes: np.ndarray,
        **params: Any,
    ) -> np.ndarray:
        """Apply transformations to bounding boxes.

        Args:
            bboxes: Bounding boxes in normalized format [x_min, y_min, x_max, y_max, class_label]
                   Values should be in range [0, 1]

        Returns:
            Transformed bounding boxes with rotation metadata [x_min, y_min, x_max, y_max, class_id, rotation_angle]
        """
        # Validate input format if not empty
        if len(bboxes) > 0 and bboxes.shape[1] < 4:
            raise ValueError(
                f"Bboxes must have at least 4 columns [x_min, y_min, x_max, y_max], got {bboxes.shape}"
            )

        # For copy-paste: bboxes are generated from the placed objects inside Rust
        # and now include rotation metadata.
        try:
            transformed = self.rust_transform.apply_to_bboxes(
                bboxes.astype(np.float32).ravel()
            )

            transformed = np.asarray(transformed, dtype=np.float32)
            if transformed.size == 0:
                return np.empty((0, 6), dtype=np.float32)

            if transformed.size % 6 != 0:
                raise ValueError(
                    "Unexpected bbox metadata size returned from Rust—expected multiples of 6"
                )

            transformed = transformed.reshape((-1, 6))

            result = np.empty_like(transformed)
            # Normalize spatial coordinates back to [0, 1]
            result[:, 0] = transformed[:, 0] / self.image_width
            result[:, 1] = transformed[:, 1] / self.image_height
            result[:, 2] = transformed[:, 2] / self.image_width
            result[:, 3] = transformed[:, 3] / self.image_height
            # Preserve class id and rotation angle (degrees)
            result[:, 4] = transformed[:, 4]
            result[:, 5] = transformed[:, 5]

            return result
        except ValueError as e:
            # Expected errors (invalid bbox format, dimension issues)
            logger.warning(f"Bbox transformation skipped due to invalid input: {e}")
            return np.empty((0, 6), dtype=np.float32)
        except RuntimeError as e:
            # Rust implementation errors
            logger.error(f"Bbox transformation failed in Rust: {e}", exc_info=True)
            raise
        except Exception as e:
            # Unexpected errors
            logger.error(f"Unexpected error in bbox transformation: {e}", exc_info=True)
            raise

    @staticmethod
    def _ensure_uint8(array: np.ndarray) -> np.ndarray:
        if array.dtype == np.uint8:
            return array
        if array.max(initial=0) <= 1.0:
            return (array * 255).astype(np.uint8)
        return array.astype(np.uint8)

    def _prepare_mask(
        self, mask: Optional[np.ndarray], height: int, width: int
    ) -> np.ndarray:
        if mask is None:
            return np.zeros((height, width, 1), dtype=np.uint8)

        mask_uint8 = self._ensure_uint8(mask)

        if mask_uint8.ndim == 2:
            mask_uint8 = mask_uint8[..., None]
        elif mask_uint8.ndim == 3 and mask_uint8.shape[2] > 1:
            mask_uint8 = mask_uint8[..., :1]

        if mask_uint8.shape[0] != height or mask_uint8.shape[1] != width:
            logger.warning(
                "Mask shape %s does not match image size (%d, %d); generating empty mask",
                mask_uint8.shape,
                height,
                width,
            )
            return np.zeros((height, width, 1), dtype=np.uint8)

        return np.ascontiguousarray(mask_uint8)

    @staticmethod
    def _normalize_mask_output(
        mask: np.ndarray, fallback: Optional[np.ndarray]
    ) -> Optional[np.ndarray]:
        mask = np.asarray(mask)
        if mask.ndim == 3 and mask.shape[2] == 1:
            return mask[..., 0].astype(np.uint8)
        if mask.ndim == 2:
            return mask.astype(np.uint8)
        if fallback is not None:
            fallback_uint8 = CopyPasteAugmentation._ensure_uint8(fallback)
            return fallback_uint8 if fallback_uint8.ndim == 2 else None
        return None

    @staticmethod
    def _resize_mask_if_needed(
        mask: np.ndarray, target_shape: tuple[int, int]
    ) -> np.ndarray:
        if mask.shape == target_shape:
            return mask

        # Fallback: best-effort resize via numpy broadcasting (nearest neighbor)
        target_height, target_width = target_shape
        height, width = mask.shape

        scale_y = max(target_height // height, 1)
        scale_x = max(target_width // width, 1)

        resized = np.repeat(np.repeat(mask, scale_y, axis=0), scale_x, axis=1)
        return resized[:target_height, :target_width]

    def get_transform_init_args_names(self) -> tuple[str, ...]:
        """Return names of arguments used to initialize the transform."""
        return (
            "image_width",
            "image_height",
            "max_paste_objects",
            "use_rotation",
            "use_scaling",
            "rotation_range",
            "scale_range",
            "use_random_background",
            "blend_mode",
            "object_counts",
            "p",
        )


# Alias for backwards compatibility
SimpleCopyPaste = CopyPasteAugmentation


__all__ = ["CopyPasteAugmentation", "SimpleCopyPaste"]
