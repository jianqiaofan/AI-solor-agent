"""正八角管截面参数、截面表增量追加和截面挑选。"""

from __future__ import annotations

import json
import math
import tempfile
import unittest
from pathlib import Path

from sap2000.check import lightest_section, member_ratio
from sap2000.sections import add_octagon_sections, octagon_tube, thickness_steps


def _solid(inradius: float) -> tuple[float, float]:
    side = 2 * inradius * math.tan(math.pi / 8)
    area = 8 * inradius**2 * math.tan(math.pi / 8)
    return area, area * (12 * inradius**2 + side**2) / 48


class SectionTests(unittest.TestCase):
    def test_area_and_inertia_match_the_regular_octagon_formulas(self) -> None:
        section = octagon_tube(165, 3.0)
        outer_area, outer_inertia = _solid(82.5)
        inner_area, inner_inertia = _solid(79.5)
        self.assertAlmostEqual(section["area_mm2"], outer_area - inner_area, places=2)
        self.assertAlmostEqual(section["I_mm4"], outer_inertia - inner_inertia, places=1)
        self.assertAlmostEqual(section["polar_moment_mm4"], 2 * section["I_mm4"], places=1)
        self.assertAlmostEqual(section["mass_kg_per_m"], section["area_mm2"] * 7850e-6, places=3)
        self.assertLess(section["W_el_corner_mm3"], section["W_el_flat_mm3"])
        self.assertGreater(section["W_pl_flat_mm3"], section["W_el_flat_mm3"])
        self.assertEqual(section["name"], "OCT165x3.0")

    def test_steps_cover_two_to_four_millimetres(self) -> None:
        steps = thickness_steps(2.0, 4.0, 0.1)
        self.assertEqual(len(steps), 21)
        self.assertEqual(steps[0], 2.0)
        self.assertEqual(steps[-1], 4.0)

    def test_table_only_adds_missing_thicknesses(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "secton-octagon-165.json"
            self.assertEqual(add_octagon_sections(path, 165, [2.0, 2.5]), ["OCT165x2.0", "OCT165x2.5"])
            table = json.loads(path.read_text(encoding="utf-8"))
            table["sections"][0]["note"] = "保留"
            path.write_text(json.dumps(table, ensure_ascii=False), encoding="utf-8")
            self.assertEqual(add_octagon_sections(path, 165, [2.0, 2.2, 2.5]), ["OCT165x2.2"])
            table = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual([item["t_mm"] for item in table["sections"]], [2.0, 2.2, 2.5])
            self.assertEqual(table["sections"][0]["note"], "保留")
            with self.assertRaises(ValueError):
                add_octagon_sections(path, 140, [2.0])

    def test_lightest_section_keeps_the_ratio_under_the_limit(self) -> None:
        sections = [octagon_tube(165, t) for t in thickness_steps(2.0, 4.0, 0.1)]
        rows = [{"case": "LRFD4_W_0_F", "P": 5, "V2": 0, "V3": 4, "T": 0, "M2": 0, "M3": -20}]
        picked = lightest_section(rows, sections, 355)
        self.assertIsNotNone(picked)
        ratio, governing = member_ratio(rows, picked, 355)
        self.assertLessEqual(ratio, 0.95)
        self.assertEqual(governing, "LRFD4_W_0_F")
        lighter = [item for item in sections if item["mass_kg_per_m"] < picked["mass_kg_per_m"]]
        self.assertTrue(all(member_ratio(rows, item, 355)[0] > 0.95 for item in lighter))
        too_big = [{"case": "X", "P": 0, "V2": 0, "V3": 0, "T": 0, "M2": 0, "M3": -100}]
        self.assertIsNone(lightest_section(too_big, sections, 355))


if __name__ == "__main__":
    unittest.main()
