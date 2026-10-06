"""Benchmark scenarios for copy-paste augmentation."""

import dataclasses

import numpy as np
import torch


@dataclasses.dataclass
class BenchmarkConfig:
    """Configuration for a benchmark scenario."""

    name: str
    image_width: int
    image_height: int
    max_paste_objects: int
    use_rotation: bool = False
    rotation_range: tuple[float, float] = (0, 360)
    scale_range: tuple[float, float] = (1.0, 1.0)
    use_random_background: bool = False
    blend_mode: str = "normal"


# Predefined benchmark scenarios
SCENARIOS = {
    "baseline_512x512_1obj": BenchmarkConfig(
        name="Baseline (512×512, 1 object)",
        image_width=512,
        image_height=512,
        max_paste_objects=1,
    ),
    "baseline_512x512_3obj": BenchmarkConfig(
        name="Baseline (512×512, 3 objects)",
        image_width=512,
        image_height=512,
        max_paste_objects=3,
    ),
    "large_1024x1024_1obj": BenchmarkConfig(
        name="Medium (1024×1024, 1 object)",
        image_width=1024,
        image_height=1024,
        max_paste_objects=1,
    ),
    "large_2048x2048_1obj": BenchmarkConfig(
        name="Large (2048×2048, 1 object)",
        image_width=2048,
        image_height=2048,
        max_paste_objects=1,
    ),
    "multi_object_5obj": BenchmarkConfig(
        name="Multi-object (512×512, 5 objects)",
        image_width=512,
        image_height=512,
        max_paste_objects=5,
    ),
    "multi_object_10obj": BenchmarkConfig(
        name="Heavy augmentation (512×512, 10 objects)",
        image_width=512,
        image_height=512,
        max_paste_objects=10,
    ),
    "with_rotation": BenchmarkConfig(
        name="With rotation (512×512, 1 object, 0-360°)",
        image_width=512,
        image_height=512,
        max_paste_objects=1,
        use_rotation=True,
        rotation_range=(0, 360),
    ),
    "with_scaling": BenchmarkConfig(
        name="With scaling (512×512, 1 object, 0.8-1.2x)",
        image_width=512,
        image_height=512,
        max_paste_objects=1,
        scale_range=(0.8, 1.2),
    ),
    "random_background": BenchmarkConfig(
        name="Random background generation",
        image_width=512,
        image_height=512,
        max_paste_objects=1,
        use_random_background=True,
    ),
    "xray_blending": BenchmarkConfig(
        name="X-ray blending (512×512, 1 object)",
        image_width=512,
        image_height=512,
        max_paste_objects=1,
        blend_mode="xray",
    ),
}


def create_dummy_image(width: int, height: int) -> np.ndarray:
    """Create a dummy image for benchmarking."""
    return np.random.randint(0, 255, (height, width, 3), dtype=np.uint8)


def create_dummy_results(width: int, height: int) -> dict:
    """Create dummy results dict for transform testing."""
    return {
        "img": create_dummy_image(width, height),
        "gt_bboxes": torch.zeros((0, 4), dtype=torch.float32),
        "gt_bboxes_labels": np.array([], dtype=np.int64),
        "gt_masks": np.zeros((0, height, width), dtype=np.uint8),
        "gt_ignore_flags": np.array([], dtype=bool),
        "img_shape": (height, width),
    }
