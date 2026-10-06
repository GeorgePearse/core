"""Tests for Albumentations-compatible CopyPasteAugmentation transform."""

import numpy as np
import pytest

try:
    import albumentations as A  # type: ignore[import-untyped]
except ImportError:
    pytest.skip("albumentations not installed", allow_module_level=True)

from copy_paste import CopyPasteAugmentation, SimpleCopyPaste
from copy_paste.transform import RUST_AVAILABLE

if not RUST_AVAILABLE:
    pytest.skip(
        "Rust extension not built; skipping CopyPasteAugmentation tests",
        allow_module_level=True,
    )


@pytest.fixture
def sample_transform():
    """Create a basic CopyPasteAugmentation transform."""
    return CopyPasteAugmentation(
        image_width=512,
        image_height=512,
        max_paste_objects=1,
        use_rotation=False,
        use_scaling=False,
        use_random_background=False,
        p=1.0,
    )


@pytest.fixture
def sample_image():
    """Create a sample image for testing."""
    return np.random.randint(0, 255, (512, 512, 3), dtype=np.uint8)


@pytest.fixture
def sample_bboxes():
    """Create sample bounding boxes in Albumentations format.

    Format: [x_min, y_min, x_max, y_max, class_label]
    Values are normalized (0-1)
    """
    return np.array(
        [
            [0.1, 0.1, 0.3, 0.3, 0],  # Class 0
            [0.5, 0.5, 0.7, 0.7, 1],  # Class 1
        ]
    )


@pytest.fixture
def sample_masks():
    """Create sample masks as a list of binary arrays."""
    return [
        np.zeros((512, 512), dtype=np.uint8),  # First mask (all zeros)
        np.zeros((512, 512), dtype=np.uint8),  # Second mask (all zeros)
    ]


def _build_toy_sample(size: int = 64) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Create a deterministic image/mask pair with two labelled objects."""
    image = np.zeros((size, size, 3), dtype=np.uint8)
    mask = np.zeros((size, size), dtype=np.uint8)
    target_mask = np.zeros((size, size), dtype=np.uint8)

    image[4:12, 4:12, 2] = 255  # class 1 (red)
    mask[4:12, 4:12] = 1

    image[20:28, 20:28, 1] = 200  # class 2 (green)
    mask[20:28, 20:28] = 2

    return image, mask, target_mask


def test_transform_initialization(sample_transform):
    """Test that transform initializes correctly."""
    assert sample_transform.image_width == 512
    assert sample_transform.image_height == 512
    assert sample_transform.max_paste_objects == 1
    assert sample_transform.p == 1.0


def test_transform_is_dual_transform(sample_transform):
    """Test that transform inherits from DualTransform."""
    assert isinstance(sample_transform, A.DualTransform)


def test_apply_basic_image(sample_transform, sample_image):
    """Test that apply method works with basic image."""
    result = sample_transform.apply(sample_image)
    assert result.shape == sample_image.shape
    assert result.dtype == sample_image.dtype


def test_apply_to_bboxes(sample_transform, sample_bboxes):
    """Test that apply_to_bboxes method works."""
    result = sample_transform.apply_to_bboxes(sample_bboxes)
    assert result.shape == (0, 6)


def test_apply_to_masks(sample_transform, sample_masks):
    """Test that apply_to_masks method works."""
    result = sample_transform.apply_to_masks(sample_masks)
    assert len(result) == len(sample_masks)


def test_full_transform_call(sample_transform, sample_image):
    """Test full transform call with Albumentations interface."""
    data = {
        "image": sample_image,
        "bboxes": np.array([[0.1, 0.1, 0.3, 0.3, 0]]),
        "masks": [np.zeros((512, 512), dtype=np.uint8)],
    }

    # Transform should handle the data through __call__
    transform_instance = sample_transform
    # We can't call the transform directly like Albumentations
    # because it's missing the full implementation, but we can call apply
    result = transform_instance.apply(data["image"])
    assert result.shape == sample_image.shape


def test_simple_copy_paste_alias():
    """Test that SimpleCopyPaste alias works."""
    transform = SimpleCopyPaste(
        image_width=256,
        image_height=256,
        max_paste_objects=1,
        p=1.0,
    )
    assert isinstance(transform, CopyPasteAugmentation)


def test_transform_with_different_sizes():
    """Test transform with various image sizes."""
    sizes = [(256, 256), (512, 512), (1024, 1024)]

    for height, width in sizes:
        transform = CopyPasteAugmentation(
            image_width=width,
            image_height=height,
            p=1.0,
        )
        image = np.random.randint(0, 255, (height, width, 3), dtype=np.uint8)
        result = transform.apply(image)
        assert result.shape == image.shape


def test_transform_probability_zero():
    """Test that transform with p=0 doesn't apply."""
    transform = CopyPasteAugmentation(
        image_width=512,
        image_height=512,
        p=0.0,  # Never apply
    )

    # When p=0, the transform's __call__ should not modify the image
    # Just testing that initialization doesn't error
    assert transform is not None


def test_transform_with_rotation():
    """Test transform with rotation enabled."""
    transform = CopyPasteAugmentation(
        image_width=512,
        image_height=512,
        use_rotation=True,
        rotation_range=(-45.0, 45.0),
        p=1.0,
    )

    image = np.random.randint(0, 255, (512, 512, 3), dtype=np.uint8)
    result = transform.apply(image)
    assert result.shape == image.shape


def test_transform_with_scaling():
    """Test transform with scaling enabled."""
    transform = CopyPasteAugmentation(
        image_width=512,
        image_height=512,
        use_scaling=True,
        scale_range=(0.8, 1.2),
        p=1.0,
    )

    image = np.random.randint(0, 255, (512, 512, 3), dtype=np.uint8)
    result = transform.apply(image)
    assert result.shape == image.shape


def test_transform_with_random_background():
    """Test transform with random background generation."""
    transform = CopyPasteAugmentation(
        image_width=512,
        image_height=512,
        use_random_background=True,
        p=1.0,
    )

    image = np.ones((512, 512, 3), dtype=np.uint8) * 50
    result = transform.apply(image)
    assert result.shape == image.shape


def test_transform_different_blend_modes():
    """Test transform with different blend modes."""
    modes = ["normal", "xray"]

    for blend_mode in modes:
        transform = CopyPasteAugmentation(
            image_width=512,
            image_height=512,
            blend_mode=blend_mode,
            p=1.0,
        )

        image = np.random.randint(0, 255, (512, 512, 3), dtype=np.uint8)
        result = transform.apply(image)
        assert result.shape == image.shape


def test_get_transform_init_args_names(sample_transform):
    """Test that get_transform_init_args_names returns correct arguments."""
    args = sample_transform.get_transform_init_args_names()

    expected_args = {
        "image_width",
        "image_height",
        "max_paste_objects",
        "use_rotation",
        "use_scaling",
        "rotation_range",
        "scale_range",
        "use_random_background",
        "blend_mode",
        "object_counts",  # Optional per-class object counts
        "p",
    }

    assert set(args) == expected_args


def test_image_dtype_handling(sample_transform):
    """Test that transform handles different image dtypes."""
    # Test uint8
    image_uint8 = np.random.randint(0, 255, (512, 512, 3), dtype=np.uint8)
    result = sample_transform.apply(image_uint8)
    assert result.dtype == np.uint8

    # Test float32 in [0, 1] range
    image_float = np.random.random((512, 512, 3)).astype(np.float32)
    result = sample_transform.apply(image_float)
    assert result.dtype == np.uint8


def test_empty_bboxes(sample_transform):
    """Test transform with empty bounding boxes."""
    empty_bboxes = np.empty((0, 5), dtype=np.float32)
    result = sample_transform.apply_to_bboxes(empty_bboxes)
    assert result.shape == (0, 6)


def test_apply_to_bboxes_with_rotation():
    """Ensure rotation metadata propagates to bbox outputs."""
    transform = CopyPasteAugmentation(
        image_width=64,
        image_height=64,
        max_paste_objects=1,
        use_rotation=True,
        rotation_range=(-45.0, -45.0),
        use_scaling=False,
        use_random_background=False,
        p=1.0,
    )

    image = np.zeros((64, 64, 3), dtype=np.uint8)
    mask = np.zeros((64, 64), dtype=np.uint8)
    mask[20:36, 20:36] = 255

    transform.apply(image, mask=mask)

    transformed_bboxes = transform.apply_to_bboxes(np.empty((0, 5), dtype=np.float32))
    assert transformed_bboxes.shape[1] == 6
    assert transformed_bboxes.shape[0] >= 1

    # Coordinates are normalized; ensure they fall inside the unit interval
    np.testing.assert_array_less(transformed_bboxes[:, :4], 1.01)
    assert np.all(transformed_bboxes[:, :4] >= 0.0)

    # Angle column should reflect the forced rotation (-45 degrees)
    assert np.isclose(transformed_bboxes[0, 5], -45.0, atol=1.0)


def test_empty_masks(sample_transform):
    """Test transform with empty masks list."""
    empty_masks = []
    result = sample_transform.apply_to_masks(empty_masks)
    assert result == []


def test_end_to_end_mask_and_bbox_outputs():
    """Verify Albumentations wrapper mirrors the Rust metadata."""
    image, mask, target_mask = _build_toy_sample()

    transform = CopyPasteAugmentation(
        image_width=image.shape[1],
        image_height=image.shape[0],
        max_paste_objects=2,
        use_rotation=False,
        use_scaling=False,
        p=1.0,
    )

    augmented = transform.apply(
        image.copy(),
        mask=mask,
        target_mask=target_mask,
    )
    assert augmented.shape == image.shape
    assert augmented.dtype == np.uint8

    bbox_metadata = transform.apply_to_bboxes(np.empty((0, 5), dtype=np.float32))
    assert bbox_metadata.shape == (2, 6)
    assert np.all(bbox_metadata[:, :4] >= 0.0) and np.all(bbox_metadata[:, :4] <= 1.0)
    assert np.all(bbox_metadata[:, 0] < bbox_metadata[:, 2])
    assert np.all(bbox_metadata[:, 1] < bbox_metadata[:, 3])
    assert set(np.round(bbox_metadata[:, 4]).astype(int)) == {1, 2}
    assert np.allclose(bbox_metadata[:, 5], 0.0, atol=1e-3)

    # Collision detection should keep pasted boxes apart.
    def _iou(box_a: np.ndarray, box_b: np.ndarray) -> float:
        x_min = max(box_a[0], box_b[0])
        y_min = max(box_a[1], box_b[1])
        x_max = min(box_a[2], box_b[2])
        y_max = min(box_a[3], box_b[3])
        if x_max <= x_min or y_max <= y_min:
            return 0.0
        intersect = (x_max - x_min) * (y_max - y_min)
        area_a = (box_a[2] - box_a[0]) * (box_a[3] - box_a[1])
        area_b = (box_b[2] - box_b[0]) * (box_b[3] - box_b[1])
        return intersect / (area_a + area_b - intersect)

    assert _iou(bbox_metadata[0, :4], bbox_metadata[1, :4]) < 0.01

    recovered_mask = transform.apply_to_mask(np.zeros_like(mask))
    assert recovered_mask.shape == mask.shape
    unique_values = set(np.unique(recovered_mask))
    assert {0, 1, 2}.issubset(unique_values)
    assert int(np.sum(recovered_mask > 0)) > 0


def test_transform_matches_full_albumentations_interface():
    """Ensure the transform can run inside an Albumentations Compose pipeline."""
    image, mask, target_mask = _build_toy_sample()

    pipeline = A.Compose(
        [
            CopyPasteAugmentation(
                image_width=image.shape[1],
                image_height=image.shape[0],
                max_paste_objects=1,
                use_rotation=False,
                use_scaling=False,
                p=1.0,
            )
        ],
        bbox_params=A.BboxParams(format="albumentations"),
        additional_targets={"target_mask": "mask"},
    )

    result = pipeline(
        image=image,
        mask=mask,
        target_mask=target_mask,
        bboxes=[],
    )

    assert result["image"].shape == image.shape
    assert result["mask"].shape == mask.shape
    # With max_paste_objects=1 and p=1.0, we expect 1 pasted object bbox
    assert len(result["bboxes"]) == 1
