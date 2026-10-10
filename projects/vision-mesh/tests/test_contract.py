"""Exercise source-derived harness functions without importing its service stack."""

import json
import re
import sys
import unittest
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any, Literal, NotRequired, TypedDict

from decoder import DecodeConfig, decode_queries

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def load_contract() -> ModuleType:
    """Execute only the checked-in, pinned pure definitions, with stdlib dependencies."""
    manifest = json.loads((FIXTURES / "upstream_contract.json").read_text())
    module = ModuleType("pinned_part_graph_contract")
    sys.modules[module.__name__] = module
    module.drawing = module
    module.__dict__.update(
        re=re,
        Counter=Counter,
        dataclass=dataclass,
        Any=Any,
        Literal=Literal,
        NotRequired=NotRequired,
        TypedDict=TypedDict,
        Rows=list,
        Sequence=list,
    )
    # Numbering precedes graph helpers; no DB, image store or service imports.
    entries = sorted(manifest["sources"], key=lambda e: "numbering.py" not in e["path"])
    for entry in entries:
        for definition in entry["definitions"].values():
            exec(compile(definition, entry["path"], "exec"), module.__dict__)
    return module


class ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.harness = load_contract()

    def test_original_upstream_link_fixture(self) -> None:
        fixture = json.loads((FIXTURES / "upstream_links.json").read_text())
        self.assertEqual(
            self.harness.plan_links(fixture["objects"]),
            {
                "e1.alt": ("key", "e1"),
                "e1.alt.pulley": ("key", "e1.alt"),
                "hose": ("number", "3.1"),
                "pipe": ("number", "7"),
            },
        )

    def test_original_upstream_consumer_fixture(self) -> None:
        fixture = json.loads((FIXTURES / "upstream_surface.json").read_text())
        objects = [
            self.harness._part_object(o, i) for i, o in enumerate(fixture["objects"])
        ]
        edges = [self.harness._part_edge(e, i) for i, e in enumerate(fixture["edges"])]
        self.assertEqual(objects, fixture["objects"])
        self.assertEqual(edges, fixture["edges"])

    def test_harness_rejects_invalid_links(self) -> None:
        for objects in (
            [{"key": "a"}, {"key": "a"}],
            [{"key": "a", "part_of": "a"}],
            [{"key": "a", "part_of": "b"}, {"key": "b", "part_of": "a"}],
            [{"key": "a", "part_of": "unknown"}],
        ):
            with self.subTest(objects=objects), self.assertRaises(ValueError):
                self.harness.plan_links(objects)
        self.assertEqual(
            self.harness.plan_links(
                [
                    {"key": "a"},
                    {"key": "b", "part_of": None},
                    {"key": "c", "part_of": ""},
                ]
            ),
            {},
        )

    def test_harness_pixel_conversion(self) -> None:
        self.assertEqual(
            self.harness._pixel_box([0.1, 0.2, 0.5, 0.6], "normalized", 1000, 500),
            (100, 100, 400, 200),
        )
        self.assertEqual(
            self.harness._pixel_box([-10, 20, 1200, 30], "pixel", 1000, 500),
            (0, 20, 1000, 10),
        )
        with self.assertRaisesRegex(ValueError, "pixels"):
            self.harness._pixel_box([100, 100, 300, 300], "normalized", 1000, 500)

    def test_repeated_objects_nested_parts_and_consumer_round_trip(self) -> None:
        # Authored synthetic logits: q2 is geometrically inside q0 but belongs
        # to q1 according to the supplied parent head. This tests decoding only.
        boxes = [
            [0, 0, 0.4, 0.6],
            [0.6, 0, 1, 0.6],
            [0.1, 0.1, 0.2, 0.2],
            [0.12, 0.12, 0.15, 0.15],
            [0.7, 0.2, 0.8, 0.3],
        ]
        classes = ["engine block", "engine block", "alternator", "pulley", "alternator"]
        scores = [
            [0, 0, 0, 0, 0, 9],
            [0, 0, 0, 0, 0, 9],
            [0, 9, 0, 0, 0, 0],
            [0, 0, 9, 0, 0, 0],
            [9, 0, 0, 0, 0, 0],
        ]
        objects = decode_queries(boxes, classes, [0.9] * 5, scores, DecodeConfig())
        objects = json.loads(json.dumps(objects))
        self.assertLessEqual(
            set(objects[0]),
            set(self.harness.PartObject.__required_keys__)
            | set(self.harness.PartObject.__optional_keys__),
        )
        links = self.harness.plan_links(objects)
        self.assertEqual(
            links, {"q2": ("key", "q1"), "q3": ("key", "q2"), "q4": ("key", "q0")}
        )

        # Simulate IDs assigned by persistence; never submit these to a DB.
        ids = {item["key"]: 100 + index for index, item in enumerate(objects)}
        rows = []
        for item in objects:
            x, y, width, height = self.harness._pixel_box(
                item["box"], "normalized", 1000, 1000
            )
            rows.append(
                SimpleNamespace(
                    id=ids[item["key"]],
                    sub_component_of=ids.get(item.get("part_of")),
                    box_x1=x,
                    box_y1=y,
                    box_width=width,
                    box_height=height,
                    class_name=item["class_name"],
                    caption=None,
                )
            )
        graph = self.harness.graph_objects(rows, 1000, 1000)
        edges = self.harness.graph_edges(rows, 1000, 1000, ["part_of"])
        self.assertEqual(
            {o["id"]: o["number"] for o in graph},
            {100: "1", 104: "1.1", 101: "2", 102: "2.1", 103: "2.1.1"},
        )
        self.assertEqual(
            {(e["source"], e["target"]) for e in edges},
            {(102, 101), (103, 102), (104, 100)},
        )
        self.assertEqual(
            [self.harness._part_object(o, i) for i, o in enumerate(graph)], graph
        )
        self.assertEqual(
            [self.harness._part_edge(e, i) for i, e in enumerate(edges)], edges
        )

    def test_harness_omits_absent_parent_from_read_graph(self) -> None:
        row = SimpleNamespace(
            id=1,
            sub_component_of=999,
            box_x1=0,
            box_y1=0,
            box_width=10,
            box_height=10,
            class_name="pulley",
            caption=None,
        )
        graph = self.harness.graph_objects([row], 100, 100)
        self.assertNotIn("part_of", graph[0])
        self.assertEqual(graph[0]["number"], "1")
        self.assertEqual(self.harness.graph_edges([row], 100, 100, ["part_of"]), [])


class DecoderTests(unittest.TestCase):
    def test_filtering_keeps_query_keys(self) -> None:
        result = decode_queries(
            [[0, 0, 1, 1]] * 3,
            ["engine block"] * 3,
            [0.8, 0.1, 0.9],
            [[0, 0, 0, 9], [0, 0, 0, 9], [9, 0, 0, 0]],
            DecodeConfig(0.8),
        )
        self.assertEqual([o["key"] for o in result], ["q0", "q2"])
        self.assertEqual(result[1]["part_of"], "q0")

    def test_invalid_structure_is_reported(self) -> None:
        for presence, scores, error in (
            ([0.9, 0.9], [[9, 0, 0], [0, 0, 9]], "itself"),
            ([0.9, 0.9], [[0, 9, 0], [9, 0, 0]], "cycle"),
            ([0.9, 0.1], [[0, 9, 0], [0, 0, 9]], "filtered"),
        ):
            with self.subTest(error=error), self.assertRaisesRegex(ValueError, error):
                decode_queries(
                    [[0, 0, 1, 1]] * 2,
                    ["engine block"] * 2,
                    presence,
                    scores,
                    DecodeConfig(),
                )

    def test_invalid_arrays_geometry_and_scores(self) -> None:
        baseline = dict(
            boxes=[[0, 0, 1, 1]],
            class_names=["pulley"],
            presence_scores=[0.9],
            parent_scores=[[0, 9]],
            config=DecodeConfig(),
        )
        for override in (
            {"class_names": []},
            {"class_names": [""]},
            {"boxes": [[0, 0, 0, 1]]},
            {"boxes": [[0, 0, float("nan"), 1]]},
            {"boxes": [[0, 0, 2, 1]]},
            {"presence_scores": [float("inf")]},
            {"presence_scores": [True]},
            {"parent_scores": [[9]]},
            {"parent_scores": [[0, float("nan")]]},
            {"config": DecodeConfig(2)},
        ):
            with self.subTest(override=override), self.assertRaises(ValueError):
                decode_queries(**(baseline | override))

    def test_empty_predictions(self) -> None:
        self.assertEqual(decode_queries([], [], [], [], DecodeConfig()), [])
        self.assertEqual(
            decode_queries([[0, 0, 1, 1]], ["pulley"], [0.1], [[0, 9]], DecodeConfig()),
            [],
        )


if __name__ == "__main__":
    unittest.main()
