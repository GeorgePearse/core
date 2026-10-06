"""Pytest benchmarks for copy-paste augmentation transforms."""

from pathlib import Path

import pytest

from benchmarks.scenarios import SCENARIOS, create_dummy_results
from copy_paste import CustomCopyPaste


@pytest.fixture
def dummy_dataset_path():
    """Get path to dummy dataset."""
    return Path(__file__).parent.parent / "tests" / "dummy_dataset"


@pytest.fixture
def annotation_file(dummy_dataset_path):
    """Get path to annotations file."""
    return dummy_dataset_path / "annotations" / "annotations.json"


def create_transform(scenario, annotation_file):
    """Create a transform for the given scenario."""
    return CustomCopyPaste(
        target_image_width=scenario.image_width,
        target_image_height=scenario.image_height,
        mm_class_list=["triangle", "circle", "square"],
        annotation_file=str(annotation_file),
        paste_prob=1.0,
        max_paste_objects=scenario.max_paste_objects,
        scale_range=scenario.scale_range,
        rotation_range=scenario.rotation_range,
        use_random_background=scenario.use_random_background,
        blend_mode=scenario.blend_mode,
        verbose=False,
    )


# Dynamically create benchmark tests for each scenario
class TestCopyPasteBenchmarks:
    """Benchmarks for CustomCopyPaste transform."""

    @pytest.mark.parametrize("scenario_name", list(SCENARIOS.keys()))
    def test_transform(self, benchmark, scenario_name, annotation_file):
        """Benchmark transform execution."""
        scenario = SCENARIOS[scenario_name]

        # Create transform
        transform = create_transform(scenario, annotation_file)

        # Create test data
        results = create_dummy_results(scenario.image_width, scenario.image_height)

        # Benchmark the transform
        def run_transform():
            return transform.transform(results.copy())

        benchmark(run_transform)


class TestTransformThroughput:
    """Throughput benchmarks (images per second)."""

    @pytest.mark.parametrize("scenario_name", list(SCENARIOS.keys()))
    def test_throughput(self, benchmark, scenario_name, annotation_file):
        """Benchmark images per second."""
        scenario = SCENARIOS[scenario_name]

        # Create transform
        transform = create_transform(scenario, annotation_file)

        # Create test data
        test_images = [
            create_dummy_results(scenario.image_width, scenario.image_height)
            for _ in range(5)
        ]

        def run_batch():
            for results in test_images:
                transform.transform(results.copy())

        # Measure time for batch
        benchmark(run_batch)


# Direct benchmark functions (not parameterized)
def test_baseline_512_1obj_direct(benchmark, annotation_file):
    """Direct benchmark: baseline 512×512, 1 object."""
    scenario = SCENARIOS["baseline_512x512_1obj"]
    transform = create_transform(scenario, annotation_file)
    results = create_dummy_results(scenario.image_width, scenario.image_height)

    benchmark(lambda: transform.transform(results.copy()))


def test_large_2048_1obj_direct(benchmark, annotation_file):
    """Direct benchmark: large 2048×2048, 1 object."""
    scenario = SCENARIOS["large_2048x2048_1obj"]
    transform = create_transform(scenario, annotation_file)
    results = create_dummy_results(scenario.image_width, scenario.image_height)

    benchmark(lambda: transform.transform(results.copy()))


def test_heavy_10obj_direct(benchmark, annotation_file):
    """Direct benchmark: 10 objects."""
    scenario = SCENARIOS["multi_object_10obj"]
    transform = create_transform(scenario, annotation_file)
    results = create_dummy_results(scenario.image_width, scenario.image_height)

    benchmark(lambda: transform.transform(results.copy()))


# Try Rust implementation if available
def test_rust_baseline_512_1obj_direct(benchmark, annotation_file):
    """Direct benchmark: Rust baseline 512×512, 1 object."""
    try:
        from copy_paste import RustCopyPaste

        scenario = SCENARIOS["baseline_512x512_1obj"]
        transform = RustCopyPaste(
            target_image_width=scenario.image_width,
            target_image_height=scenario.image_height,
            mm_class_list=["triangle", "circle", "square"],
            annotation_file=str(annotation_file),
            paste_prob=1.0,
            max_paste_objects=scenario.max_paste_objects,
            scale_range=scenario.scale_range,
            rotation_range=scenario.rotation_range,
            use_random_background=scenario.use_random_background,
        )
        results = create_dummy_results(scenario.image_width, scenario.image_height)

        benchmark(lambda: transform.transform(results.copy()))
    except RuntimeError:
        pytest.skip("RustCopyPaste not available")
