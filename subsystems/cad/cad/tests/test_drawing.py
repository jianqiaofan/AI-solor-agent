"""线模立面只含主梁、立柱，以及间距、总长和高度。"""

from __future__ import annotations

import unittest

from cad.drawing import (
    CHAIN_OFFSET_MM,
    HEIGHT_OFFSET_MM,
    OVERALL_OFFSET_MM,
    plan,
)


def _model() -> dict:
    return {
        "kind": "line_model",
        "units": "mm",
        "h_mm": 1400,
        "length_mm": 10000,
        "beam": {"start": [0, 0, 1400], "end": [0, 10000, 1400]},
        "columns": [
            {
                "index": 1,
                "kind": "plain",
                "y_mm": 1000,
                "bottom": [0, 1000, 0],
                "top": [0, 1000, 1400],
            },
            {
                "index": 2,
                "kind": "drive",
                "y_mm": 6000,
                "bottom": [0, 6000, 0],
                "top": [0, 6000, 1400],
            },
            {
                "index": 3,
                "kind": "plain",
                "y_mm": 9000.2,
                "bottom": [0, 9000.2, 0],
                "top": [0, 9000.2, 1400],
            },
        ],
        "issues": [],
    }


class PlanTests(unittest.TestCase):
    def test_elevation_uses_beam_length_as_x_and_height_as_y(self) -> None:
        view = plan(_model())
        self.assertEqual(view["decimals"], 1)
        self.assertEqual(
            [(item["layer"], item["start"], item["end"]) for item in view["lines"]],
            [
                ("主梁", (0.0, 1400.0, 0.0), (10000.0, 1400.0, 0.0)),
                ("立柱", (1000.0, 0.0, 0.0), (1000.0, 1400.0, 0.0)),
                ("驱动立柱", (6000.0, 0.0, 0.0), (6000.0, 1400.0, 0.0)),
                ("立柱", (9000.2, 0.0, 0.0), (9000.2, 1400.0, 0.0)),
            ],
        )
        chain = view["dimensions"][:-2]
        self.assertEqual(
            [(item["start"][0], item["end"][0], item["at"][1]) for item in chain],
            [
                (0.0, 1000.0, 1400.0 + CHAIN_OFFSET_MM),
                (1000.0, 6000.0, 1400.0 + CHAIN_OFFSET_MM),
                (6000.0, 9000.2, 1400.0 + CHAIN_OFFSET_MM),
                (9000.2, 10000.0, 1400.0 + CHAIN_OFFSET_MM),
            ],
        )
        overall = view["dimensions"][-2]
        self.assertEqual(overall["start"], (0.0, 1400.0, 0.0))
        self.assertEqual(overall["end"], (10000.0, 1400.0, 0.0))
        self.assertEqual(overall["at"][1], 1400.0 + OVERALL_OFFSET_MM)
        height = view["dimensions"][-1]
        self.assertEqual(height["start"], (1000.0, 0.0, 0.0))
        self.assertEqual(height["end"], (1000.0, 1400.0, 0.0))
        self.assertAlmostEqual(height["at"][0], 1000.0 - HEIGHT_OFFSET_MM)

    def test_integer_lengths_use_no_decimal(self) -> None:
        model = _model()
        model["columns"][2]["y_mm"] = 9000
        model["columns"][2]["bottom"][1] = 9000
        model["columns"][2]["top"][1] = 9000
        self.assertEqual(plan(model)["decimals"], 0)

    def test_unresolved_line_model_is_not_drawn(self) -> None:
        model = _model()
        model["issues"] = ["起点到驱动立柱放不下。"]
        with self.assertRaises(ValueError):
            plan(model)

    def test_missing_columns_are_not_drawn(self) -> None:
        model = _model()
        model["columns"] = []
        with self.assertRaises(ValueError):
            plan(model)
