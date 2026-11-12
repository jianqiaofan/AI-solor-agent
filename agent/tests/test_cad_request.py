"""生成 CAD 图纸时打开 AutoCAD，把当前线模画成立面。没有线模就先布置。"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent.cad_request import answer_cad_request, resolve_cad_intent
from agent.intent import CHAT, DESIGN, SAP, WIND

_PACKAGE = Path(__file__).resolve().parents[2] / "subsystems" / "cad"
if str(_PACKAGE) not in sys.path:
    sys.path.insert(0, str(_PACKAGE))


def _case() -> dict:
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
    return sample


class CadIntentTests(unittest.TestCase):
    def test_drawing_request_opens_cad(self) -> None:
        self.assertEqual(resolve_cad_intent(CHAT, "生成CAD图纸", []), "draw_cad")
        self.assertEqual(resolve_cad_intent(CHAT, "打开CAD把线模画上去", []), "draw_cad")
        self.assertEqual(resolve_cad_intent(DESIGN, "出图", []), "draw_cad")

    def test_meaning_question_stays_chat(self) -> None:
        self.assertEqual(resolve_cad_intent(CHAT, "什么是CAD", []), CHAT)
        self.assertEqual(resolve_cad_intent("draw_cad", "图纸是什么意思", []), CHAT)

    def test_loads_and_sap_stay_ahead_of_drawing(self) -> None:
        self.assertEqual(resolve_cad_intent(WIND, "计算风荷载并出图", []), WIND)
        self.assertEqual(resolve_cad_intent(SAP, "调用SAP2000", []), SAP)
        self.assertEqual(resolve_cad_intent(CHAT, "计算内力", []), CHAT)

    def test_follow_up_after_a_gap_continues_the_drawing(self) -> None:
        messages = [
            {"role": "assistant", "content": "还不能生成 CAD 图纸。\n还缺最小离地高度。"},
            {"role": "user", "content": "离地高度改为 800"},
        ]
        self.assertEqual(resolve_cad_intent(CHAT, "离地高度改为 800", messages), "draw_cad")


class CadRequestTests(unittest.TestCase):
    def test_missing_geometry_does_not_open_cad(self) -> None:
        case = _case()
        case["geometry"].pop("ground_clearance_mm")
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "design_case.json"
            path.write_text(json.dumps(case, ensure_ascii=False), encoding="utf-8")
            with patch("cad.session.draw_line_model") as draw:
                reply, wrote, show = answer_cad_request(
                    path.read_text(encoding="utf-8"),
                    "甲项目",
                    [{"role": "user", "content": "生成CAD图纸"}],
                    path,
                )
        self.assertTrue(reply.startswith("还不能生成 CAD 图纸。"))
        self.assertFalse(show)
        self.assertFalse(draw.called)

    def test_draws_the_current_line_model(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "design_case.json"
            path.write_text(json.dumps(_case(), ensure_ascii=False), encoding="utf-8")
            with patch("cad.session.draw_line_model", return_value=Path(r"D:\AutoCAD\acad.exe")) as draw:
                reply, wrote, show = answer_cad_request(
                    path.read_text(encoding="utf-8"),
                    "甲项目",
                    [{"role": "user", "content": "生成CAD图纸"}],
                    path,
                )
            self.assertTrue(wrote)
            self.assertFalse(show)
            self.assertIn("已打开 AutoCAD", reply)
            self.assertIn("projects/甲项目/成果/CAD/line_model.dwg", reply)
            self.assertIn("尺寸标了各段间距", reply)
            model, destination = draw.call_args.args
            self.assertEqual(model["kind"], "line_model")
            self.assertEqual(destination, Path(folder) / "CAD" / "line_model.dwg")
            self.assertTrue((Path(folder) / "line_model.json").is_file())

    def test_same_line_model_is_not_rebuilt_before_drawing(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "design_case.json"
            path.write_text(json.dumps(_case(), ensure_ascii=False), encoding="utf-8")
            with patch("cad.session.draw_line_model", return_value=Path(r"D:\AutoCAD\acad.exe")):
                first = answer_cad_request(
                    path.read_text(encoding="utf-8"),
                    "甲项目",
                    [{"role": "user", "content": "生成CAD图纸"}],
                    path,
                )
            self.assertTrue(first[1])
            with patch("cad.session.draw_line_model", return_value=Path(r"D:\AutoCAD\acad.exe")) as draw:
                with patch("agent.cad_request.answer_line_model") as layout:
                    reply, wrote, show = answer_cad_request(
                        path.read_text(encoding="utf-8"),
                        "甲项目",
                        [{"role": "user", "content": "再出一次图"}],
                        path,
                    )
            self.assertIn("已打开 AutoCAD", reply)
            self.assertTrue(wrote)
            self.assertFalse(show)
            self.assertFalse(layout.called)
            self.assertEqual(draw.call_args.args[0]["kind"], "line_model")
