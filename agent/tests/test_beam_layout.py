"""主梁立柱布置和立面图。"""

from __future__ import annotations

import math
import unittest

from agent.beam_drawing import render_svg
from agent.beam_layout import arrange, layout_view


class SymmetricTrackerTests(unittest.TestCase):
    def test_drive_sits_at_the_gap_midpoint_and_bays_are_5000(self) -> None:
        layout = arrange(2384, 1134, 800, [22, 22], "22/22")
        pitch = 1134 + 20
        drive = 22 * pitch + 250
        self.assertAlmostEqual(layout.length_mm, 22 * pitch * 2 + 500)
        self.assertAlmostEqual(layout.h_mm, 0.5 * 2384 * math.cos(math.radians(60)) + 800)
        self.assertEqual(
            [column.kind for column in layout.columns],
            ["plain"] * 5 + ["drive"] + ["plain"] * 5,
        )
        self.assertAlmostEqual(layout.columns[5].y_mm, drive)
        self.assertEqual(layout.columns[5].drive_index, 1)
        expected = [638 + index * 5000 for index in range(5)]
        expected.append(drive)
        expected.extend(drive + index * 5000 for index in range(1, 6))
        for column, y_mm in zip(layout.columns, expected):
            self.assertAlmostEqual(column.y_mm, y_mm)
        self.assertAlmostEqual(layout.overhang_start_mm, 638)
        self.assertAlmostEqual(layout.overhang_end_mm, 638)
        self.assertEqual(layout.issues, ())

    def test_interior_bay_stays_equal_when_it_is_not_a_multiple_of_100(self) -> None:
        layout = arrange(2384, 1134, 800, [22, 22, 22], "22/22/22")
        drives = [column for column in layout.columns if column.kind == "drive"]
        self.assertEqual(len(drives), 2)
        interior = drives[1].y_mm - drives[0].y_mm
        self.assertAlmostEqual(interior, 25888)
        between = [
            column.y_mm
            for column in layout.columns
            if drives[0].y_mm < column.y_mm < drives[1].y_mm
        ]
        self.assertEqual(len(between), 4)
        self.assertAlmostEqual(between[0] - drives[0].y_mm, interior / 5)
        self.assertAlmostEqual(drives[1].y_mm - between[-1], interior / 5)
        self.assertAlmostEqual(layout.overhang_start_mm, 600)
        self.assertAlmostEqual(layout.overhang_end_mm, 600)
        self.assertEqual(layout.issues, ())


class PlainBeamTests(unittest.TestCase):
    def test_equal_bays_use_a_5000_spacing(self) -> None:
        layout = arrange(2000, 1300, 500, [20], "20")
        self.assertAlmostEqual(layout.length_mm, 26400)
        self.assertEqual([column.kind for column in layout.columns], ["plain"] * 6)
        self.assertAlmostEqual(layout.columns[0].y_mm, 700)
        self.assertAlmostEqual(layout.columns[1].y_mm - layout.columns[0].y_mm, 5000)
        self.assertAlmostEqual(layout.overhang_end_mm, 700)
        self.assertEqual(layout.issues, ())


class ConflictTests(unittest.TestCase):
    def test_eleven_twenty_two_now_places_plain_columns(self) -> None:
        view = layout_view(
            {
                "module_length_mm": 2384,
                "module_width_mm": 1303,
                "ground_clearance_mm": 800,
                "arrangement_columns": "11/22",
            }
        )
        self.assertTrue(view["ready"])
        self.assertEqual(view["issues"], [])
        self.assertEqual(
            [column["kind"] for column in view["columns"]],
            ["plain", "plain", "drive", "plain", "plain", "plain", "plain"],
        )
        self.assertAlmostEqual(view["columns"][2]["y_mm"], 11 * (1303 + 20) + 250)
        self.assertAlmostEqual(view["overhang_start_mm"], 803)
        self.assertAlmostEqual(view["columns"][1]["y_mm"] - view["columns"][0]["y_mm"], 7000)

    def test_short_side_keeps_the_drive_and_reports_both_ends(self) -> None:
        view = layout_view(
            {
                "module_length_mm": 2384,
                "module_width_mm": 1134,
                "ground_clearance_mm": 800,
                "arrangement_columns": "3/3",
            }
        )
        self.assertTrue(view["ready"])
        self.assertEqual(len(view["issues"]), 2)
        self.assertEqual([column["kind"] for column in view["columns"]], ["drive"])
        self.assertAlmostEqual(view["columns"][0]["y_mm"], 3 * (1134 + 20) + 250)
        self.assertIn("驱动", view["svg"])
        self.assertIn("5000–10000", view["issues"][0])
        self.assertIn("600–1600", view["issues"][0])

    def test_missing_geometry_does_not_invent_a_drawing(self) -> None:
        view = layout_view({"module_length_mm": 2384, "arrangement_columns": "22/22"})
        self.assertFalse(view["ready"])
        self.assertNotIn("svg", view)
        self.assertIn("组件宽度", view["message"])

    def test_broken_arrangement_is_rejected(self) -> None:
        view = layout_view(
            {
                "module_length_mm": 2384,
                "module_width_mm": 1134,
                "ground_clearance_mm": 800,
                "arrangement_columns": "22/",
            }
        )
        self.assertFalse(view["ready"])


class DrawingTests(unittest.TestCase):
    def test_svg_names_the_beam_and_both_column_kinds(self) -> None:
        layout = arrange(2384, 1134, 800, [22, 22], "22/22")
        svg = render_svg(layout)
        self.assertIn("<svg", svg)
        self.assertIn("主梁", svg)
        self.assertIn("驱动立柱", svg)
        self.assertIn("非驱动立柱", svg)
        self.assertIn("638", svg)
        self.assertIn("5000", svg)


if __name__ == "__main__":
    unittest.main()
