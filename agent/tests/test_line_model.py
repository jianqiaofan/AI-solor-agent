"""设计支架时只布置线模。"""

from __future__ import annotations

import json
import math
import tempfile
import unittest
from pathlib import Path

from agent.intent import CHAT, DESIGN, UPDATE, WIND
from agent.line_model import answer_line_model, resolve_design_intent
from agent.load_check import collect_updates


class DesignIntentTests(unittest.TestCase):
    def test_design_request_becomes_line_model(self) -> None:
        self.assertEqual(resolve_design_intent(CHAT, "帮我设计支架", []), DESIGN)
        self.assertEqual(resolve_design_intent(CHAT, "先出线模", []), DESIGN)

    def test_meaning_question_stays_chat(self) -> None:
        self.assertEqual(resolve_design_intent(CHAT, "什么是线模", []), CHAT)

    def test_load_request_stays_ahead_of_design(self) -> None:
        self.assertEqual(resolve_design_intent(WIND, "设计支架并计算风荷载", []), WIND)
        self.assertEqual(resolve_design_intent(DESIGN, "设计支架并计算风荷载", []), WIND)

    def test_follow_up_after_a_gap_continues_the_line_model(self) -> None:
        messages = [
            {"role": "assistant", "content": "还不能设计支架线模。还缺最小离地高度。"},
            {"role": "user", "content": "离地高度改为 800"},
        ]
        self.assertEqual(resolve_design_intent(UPDATE, "离地高度改为 800", messages), DESIGN)

    def test_unrelated_edit_is_not_a_design(self) -> None:
        self.assertEqual(resolve_design_intent(UPDATE, "风速改为 25", []), UPDATE)

    def test_row_arrangement_change_is_recognized(self) -> None:
        self.assertEqual(
            collect_updates("将每排的排布从11/22改为22/22")["geometry.arrangement_columns"],
            "22/22",
        )
        both = collect_updates("将排数改为1排，每排改为22/22")
        self.assertEqual(both["geometry.arrangement_rows"], 1)
        self.assertEqual(both["geometry.arrangement_columns"], "22/22")
        self.assertEqual(
            collect_updates("支架已由11/22，改为22/22")["geometry.arrangement_columns"],
            "22/22",
        )


class LineModelTests(unittest.TestCase):
    def test_missing_geometry_does_not_write(self) -> None:
        from agent.settings import ROOT

        sample = json.loads((ROOT / "fixtures" / "design_case.sample.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "design_case.json"
            path.write_text(json.dumps(sample), encoding="utf-8")
            reply, wrote, show = answer_line_model(
                path.read_text(encoding="utf-8"),
                "甲项目",
                [{"role": "user", "content": "设计支架"}],
                path,
            )
            self.assertFalse(wrote)
            self.assertFalse(show)
            self.assertTrue(reply.startswith("还不能设计支架线模"))
            self.assertFalse((Path(folder) / "line_model.json").exists())

    def test_writes_centerlines_without_sections_or_loads(self) -> None:
        from agent.settings import ROOT

        sample = json.loads((ROOT / "fixtures" / "design_case.sample.json").read_text(encoding="utf-8"))
        sample["geometry"].update(
            {
                "module_length_mm": 2384,
                "module_width_mm": 1134,
                "ground_clearance_mm": 800,
                "arrangement_columns": "22/22",
            }
        )
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "design_case.json"
            path.write_text(json.dumps(sample, ensure_ascii=False), encoding="utf-8")
            reply, wrote, show = answer_line_model(
                path.read_text(encoding="utf-8"),
                "甲项目",
                [{"role": "user", "content": "设计支架"}],
                path,
            )
            self.assertTrue(wrote)
            self.assertTrue(show)
            self.assertIn("没有选截面", reply)
            self.assertIn("没有加荷载", reply)
            self.assertIn("没有运行 SAP2000", reply)
            self.assertIn("projects/甲项目/成果/line_model.json", reply)
            pitch = 1134 + 20
            drive = 22 * pitch + 250
            height = 0.5 * 2384 * math.cos(math.radians(60)) + 800
            saved = json.loads((Path(folder) / "line_model.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["kind"], "line_model")
            self.assertEqual(saved["tilt_angle_deg"], 60)
            self.assertNotIn("section", saved)
            self.assertNotIn("loads", saved)
            self.assertEqual(saved["beam"]["start"], [0, 0, height])
            self.assertAlmostEqual(saved["length_mm"], 22 * pitch * 2 + 500)
            self.assertEqual(
                [item["kind"] for item in saved["columns"]],
                ["plain"] * 5 + ["drive"] + ["plain"] * 5,
            )
            self.assertAlmostEqual(saved["columns"][5]["y_mm"], drive)
            self.assertEqual(saved["columns"][0]["bottom"][2], 0)
            self.assertAlmostEqual(saved["columns"][0]["top"][2], height)
            self.assertIn("是 100 的整数倍", reply)
            self.assertIn(str(int(round(drive))), reply)

    def test_same_sentence_can_fill_clearance_before_layout(self) -> None:
        from agent.settings import ROOT

        sample = json.loads((ROOT / "fixtures" / "design_case.sample.json").read_text(encoding="utf-8"))
        sample["geometry"].update(
            {
                "module_length_mm": 2384,
                "module_width_mm": 1134,
                "arrangement_columns": "22/22",
            }
        )
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "design_case.json"
            path.write_text(json.dumps(sample, ensure_ascii=False), encoding="utf-8")
            reply, wrote, show = answer_line_model(
                path.read_text(encoding="utf-8"),
                "甲项目",
                [{"role": "user", "content": "设计支架，离地高度改为 800"}],
                path,
            )
            self.assertTrue(show)
            self.assertTrue(wrote)
            self.assertIn("已写入 projects/甲项目/成果/design_case.json", reply)
            saved_case = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(saved_case["geometry"]["ground_clearance_mm"], 800)
            self.assertTrue((Path(folder) / "line_model.json").is_file())

    def test_design_uses_the_arrangement_changed_in_the_same_sentence(self) -> None:
        from agent.settings import ROOT

        sample = json.loads((ROOT / "fixtures" / "design_case.sample.json").read_text(encoding="utf-8"))
        sample["geometry"].update(
            {
                "module_length_mm": 2384,
                "module_width_mm": 1303,
                "ground_clearance_mm": 800,
                "arrangement_columns": "11/22",
            }
        )
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "design_case.json"
            path.write_text(json.dumps(sample, ensure_ascii=False), encoding="utf-8")
            reply, wrote, show = answer_line_model(
                path.read_text(encoding="utf-8"),
                "aaa",
                [{"role": "user", "content": "设计支架。每排的排布从11/22改为22/22"}],
                path,
            )
            self.assertTrue(wrote)
            self.assertTrue(show)
            saved_case = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(saved_case["geometry"]["arrangement_columns"], "22/22")
            saved = json.loads((path.parent / "line_model.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["arrangement_columns"], "22/22")
            self.assertIn("22 * (1303 + 20) + 500 + 22 * (1303 + 20)", reply)
            self.assertNotIn("11 * (1303 + 20)", reply)
