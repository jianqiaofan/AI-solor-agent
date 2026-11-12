"""线模分段、线荷载和最大内力不依赖 SAP2000 进程。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from sap2000.model import (
    beam_line_loads,
    extreme_forces,
    members_from_line_model,
    report,
)
from sap2000.runner import run_design


def _line_model() -> dict:
    return {
        "units": "mm",
        "issues": [],
        "beam": {"start": [0, 0, 1000], "end": [0, 10000, 1000]},
        "columns": [
            {
                "index": 1,
                "kind": "plain",
                "y_mm": 5000,
                "bottom": [0, 5000, 0],
                "top": [0, 5000, 1000],
            }
        ],
    }


class ModelTests(unittest.TestCase):
    def test_beam_is_split_at_each_column(self) -> None:
        members = members_from_line_model(_line_model())
        self.assertEqual([item["id"] for item in members], ["B1", "B2", "C1"])
        self.assertEqual(members[0]["role"], "beam")
        self.assertAlmostEqual(members[0]["length"], 5)
        self.assertAlmostEqual(members[2]["length"], 1)
        self.assertEqual(members[2]["base"], (0, 5, 0))

    def test_only_beam_line_loads_are_sent(self) -> None:
        loads = {
            "cases": [
                {"id": "W_QP_0", "target": "module", "value": 0.6, "unit": "kN/m2"},
                {"id": "D_LINE", "target": "beam", "value": 0.2, "unit": "kN/m"},
                {"id": "W_0_F_LINE", "target": "beam", "value": -1.5, "unit": "kN/m"},
            ]
        }
        cases = beam_line_loads(loads)
        self.assertEqual([item["id"] for item in cases], ["D_LINE", "W_0_F_LINE"])
        self.assertEqual(cases[0]["pattern"], 1)
        self.assertEqual(cases[1]["pattern"], 6)

    def test_extreme_keeps_the_signed_value_with_the_largest_magnitude(self) -> None:
        forces = extreme_forces(
            [
                {"P": 1, "V2": 0, "V3": 2, "T": 0, "M2": 0.2, "M3": -3},
                {"P": -4, "V2": 0, "V3": -1, "T": 0, "M2": -0.1, "M3": 2},
            ]
        )
        self.assertEqual(forces["N"], -4)
        self.assertEqual(forces["Vz"], 2)
        self.assertEqual(forces["Mz"], -3)

    def test_runner_selects_sections_and_checks_them_again_without_opening_sap(self) -> None:
        class FakeSession:
            def __init__(self) -> None:
                self.solved: list[dict[str, str]] = []

            def build(self, members, cases, combinations, table, model_path):
                self.members = [item["id"] for item in members]
                self.first = {item["id"]: item["section"] for item in members}
                self.cases = [item["id"] for item in cases]
                self.self_weight = {item["id"]: item["self_weight"] for item in cases}
                self.combinations = [item["id"] for item in combinations]

            def solve(self, assignment):
                self.solved.append(dict(assignment))
                return {
                    member: [
                        {"case": "D_LINE", "P": 0, "V2": 0, "V3": 1.25, "T": 0, "M2": 0, "M3": -2.0},
                        {"case": "LRFD1", "P": 3, "V2": 0, "V3": 4.0, "T": 0, "M2": 0, "M3": -20.0},
                    ]
                    for member in assignment
                }

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "line_model.json").write_text(json.dumps(_line_model()), encoding="utf-8")
            session = FakeSession()
            result, design = run_design(
                {"revision": "r0"},
                {
                    "cases": [
                        {"id": "D", "target": "module", "value": 0.1, "unit": "kN/m2"},
                        {"id": "D_LINE", "target": "beam", "value": 0.2, "unit": "kN/m"},
                    ],
                    "combinations": [],
                },
                root / "sap",
                session,
            )
        self.assertEqual(session.members, ["B1", "B2", "C1"])
        self.assertEqual(set(session.first.values()), {"OCT165x2.0"})
        self.assertEqual(session.cases, ["D_LINE"])
        self.assertEqual(session.self_weight, {"D_LINE": 1.0})
        self.assertEqual(session.combinations, ["LRFD1"])
        self.assertEqual(len(session.solved), 2)
        picked = session.solved[1]["B1"]
        self.assertNotEqual(picked, "OCT165x2.0")
        self.assertEqual(result["check_status"], "passed")
        self.assertEqual(result["members"][0]["section"], picked)
        self.assertLessEqual(result["members"][0]["ratio"], 0.95)
        self.assertEqual(result["members"][0]["forces"]["Mz"], -20.0)
        self.assertEqual(result["reactions"], [])
        self.assertEqual(design["members"][0]["governing"], "LRFD1")
        self.assertEqual(design["combinations"], [{"id": "LRFD1", "formula": "1.4D"}])
        self.assertEqual(len(design["rounds"]), 2)
        text = report(result, "SAP2000.exe", design)
        self.assertIn("设计合格", text)
        self.assertIn("### 主梁", text)
        self.assertIn("| 编号 | L (m) | 截面 | 应力比 | 控制工况 |", text)
        self.assertIn("| B1 |", text)
        self.assertIn("| C1 |", text)
        self.assertNotIn("B1  L=", text)
