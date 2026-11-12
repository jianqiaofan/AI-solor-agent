"""调用 SAP2000 前先备齐荷载和线模。齐备后弹出对话框，点击确认才调用。draft 也可以调用。"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent.intent import CHAT, DESIGN, LOADS
from agent.sap_request import answer_sap_request, resolve_sap_intent

_PACKAGE = Path(__file__).resolve().parents[2] / "subsystems" / "loads_sap2000"
if str(_PACKAGE) not in sys.path:
    sys.path.insert(0, str(_PACKAGE))


def _calculated_result() -> tuple[dict, dict]:
    result = {
        "schema_version": "1.0.0",
        "design_case_revision": "r0",
        "model_file": "model.sdb",
        "template": "line-model",
        "check_status": "passed",
        "members": [
            {
                "id": "B1",
                "section": "OCT165x2.0",
                "length": 1.0,
                "forces": {"N": 0.0, "Vy": 0.0, "Vz": 1.5, "T": 0.0, "My": 0.0, "Mz": -2.5},
                "ratio": 0.42,
            }
        ],
        "reactions": [],
        "displacements": [],
    }
    design = {
        "table": "secton-octagon-165.json",
        "material": "Q355B",
        "fy_mpa": 355.0,
        "phi": 0.9,
        "select_limit": 0.95,
        "accept_limit": 1.0,
        "combination_basis": "ASCE 7-16 第 2.3.1 节强度设计（LRFD）",
        "combinations": [{"id": "LRFD1", "formula": "1.4D"}],
        "rounds": [{"round": 1, "sections": {"B1": "OCT165x2.0"}, "ratios": {"B1": 0.42}}],
        "members": [{"id": "B1", "section": "OCT165x2.0", "ratio": 0.42, "governing": "LRFD1"}],
        "total_mass_kg": 8.48,
        "message": "",
    }
    return result, design


def _ready_case() -> dict:
    return {
        "schema_version": "1.0.0",
        "project_id": "SAMPLE",
        "revision": "r0",
        "status": "confirmed",
        "code_pack": "Europe(Eurocode 1991-4)",
        "site": {
            "design_code": "Europe(Eurocode 1991-4)",
            "wind_speed": 25.3,
            "wind_speed_unit": "m/s",
            "wind_speed_averaging": "10 min mean",
            "snow_load": 1.5,
            "snow_load_unit": "KN/m2",
            "risk_category": "I",
            "terrain_category": "II",
            "snow_exposure": "windswept",
        },
        "geometry": {
            "module_length_mm": 2384,
            "module_width_mm": 1134,
            "module_weight_kg": 37.7,
            "ground_clearance_mm": 800,
            "arrangement_columns": "22/22",
            "arrangement_rows": 1,
        },
    }


class SapIntentTests(unittest.TestCase):
    def test_sap_request_is_not_a_load_or_a_line_model(self) -> None:
        self.assertEqual(resolve_sap_intent(CHAT, "调用SAP2000", []), "run_sap2000")
        self.assertEqual(resolve_sap_intent(LOADS, "计算内力", []), "run_sap2000")
        self.assertEqual(resolve_sap_intent(CHAT, "计算荷载", []), CHAT)
        self.assertEqual(resolve_sap_intent(DESIGN, "设计支架", []), DESIGN)
        self.assertEqual(resolve_sap_intent(CHAT, "什么是内力", []), CHAT)

    def test_follow_up_stays_on_sap(self) -> None:
        asking = [
            {"role": "assistant", "content": "还不能调用 SAP2000。\n还不能计算风荷载。"},
            {"role": "user", "content": "地形类别 II，暴露条件 windswept"},
        ]
        self.assertEqual(
            resolve_sap_intent(CHAT, "地形类别 II，暴露条件 windswept", asking),
            "run_sap2000",
        )
        holding = [
            {"role": "assistant", "content": "线模和荷载已经齐备。请在对话框里点击确认。点击确认之后才调用 SAP2000。"},
            {"role": "user", "content": "确认"},
        ]
        self.assertEqual(resolve_sap_intent(CHAT, "确认", holding), "run_sap2000")


class SapRequestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ran = patch("sap2000.runner.run_design", return_value=_calculated_result()).start()
        self.addCleanup(patch.stopall)

    def test_missing_parameters_are_asked_and_sap_is_not_called(self) -> None:
        from agent.settings import ROOT

        sample = json.loads((ROOT / "fixtures" / "design_case.sample.json").read_text(encoding="utf-8"))
        sample["site"]["design_code"] = "Europe(Eurocode 1991-4)"
        sample["status"] = "confirmed"
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "design_case.json"
            path.write_text(json.dumps(sample, ensure_ascii=False), encoding="utf-8")
            reply, _wrote, show, dialog = answer_sap_request(
                path.read_text(encoding="utf-8"),
                "甲项目",
                [{"role": "user", "content": "调用SAP2000"}],
                path,
            )
            self.assertTrue(reply.startswith("还不能调用 SAP2000"))
            self.assertIn("还不能设计支架线模", reply)
            self.assertIn("还不能计算", reply)
            self.assertNotIn("这次没有运行", reply)
            self.assertFalse(self.ran.called)
            self.assertNotIn("确认之前不会调用", reply)
            self.assertFalse(show)
            self.assertFalse(dialog)
            self.assertFalse((path.parent / "loads.json").exists())
            self.assertFalse((path.parent / "analysis_result.json").exists())

    def test_new_results_wait_for_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "design_case.json"
            path.write_text(json.dumps(_ready_case(), ensure_ascii=False), encoding="utf-8")
            reply, wrote, show, dialog = answer_sap_request(
                path.read_text(encoding="utf-8"),
                "甲项目",
                [{"role": "user", "content": "调用 SAP2000 做结构计算"}],
                path,
            )
            self.assertTrue(wrote)
            self.assertTrue(show)
            self.assertTrue(dialog)
            self.assertIn("点击确认之后才调用 SAP2000", reply)
            self.assertNotIn("SAP2000.exe", reply)
            self.assertIn("组件自重", reply)
            self.assertTrue((path.parent / "line_model.json").is_file())
            self.assertTrue((path.parent / "loads.json").is_file())
            self.assertFalse((path.parent / "analysis_result.json").exists())
            saved = json.loads((path.parent / "loads.json").read_text(encoding="utf-8"))
            by_id = {item["id"]: item for item in saved["cases"]}
            self.assertIn("D", by_id)
            self.assertIn("D_LINE", by_id)
            self.assertEqual(by_id["D_LINE"]["unit"], "kN/m")
            self.assertEqual(by_id["D_LINE"]["target"], "beam")
            self.assertEqual(by_id["D_LINE"]["value"], round(by_id["D"]["value"] * 2.384, 4))
            self.assertNotIn("W_QP_0_LINE", by_id)
            self.assertIn("W_0_F_LINE", by_id)
            self.assertIn("S_0_LINE", by_id)
            self.assertTrue(any(item.startswith("W_") for item in by_id))
            self.assertTrue(any(item.startswith("S_") for item in by_id))
            self.assertIn("主梁线荷载", reply)
            combos = {item["id"]: item["factors"] for item in saved["combinations"]}
            self.assertEqual(combos["LRFD1"], [{"case_id": "D", "factor": 1.4}])
            self.assertIn("LRFD5_W_0_F", combos)
            self.assertIn("LRFD4_W_0_F_S_0", combos)
            self.assertNotIn("LRFD4_W_60_0_F_S_0", combos)

    def test_confirmation_reaches_sap_without_inventing_forces(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "design_case.json"
            path.write_text(json.dumps(_ready_case(), ensure_ascii=False), encoding="utf-8")
            first, _wrote, _show, first_dialog = answer_sap_request(
                path.read_text(encoding="utf-8"),
                "甲项目",
                [{"role": "user", "content": "计算内力"}],
                path,
            )
            reply, wrote, show, dialog = answer_sap_request(
                path.read_text(encoding="utf-8"),
                "甲项目",
                [
                    {"role": "user", "content": "计算内力"},
                    {"role": "assistant", "content": first},
                    {"role": "user", "content": "确认"},
                ],
                path,
            )
            self.assertTrue(first_dialog)
            self.assertFalse(wrote)
            self.assertFalse(show)
            self.assertTrue(dialog)
            self.assertNotIn("SAP2000.exe", reply)
            called, called_wrote, called_show, called_dialog = answer_sap_request(
                path.read_text(encoding="utf-8"),
                "甲项目",
                [
                    {"role": "user", "content": "计算内力"},
                    {"role": "assistant", "content": first},
                    {"role": "user", "content": "确认调用 SAP2000"},
                ],
                path,
                True,
            )
            self.assertTrue(called_wrote)
            self.assertFalse(called_show)
            self.assertFalse(called_dialog)
            self.assertIn("已用 SAP2000 完成计算", called)
            self.assertIn("SAP2000.exe", called)
            self.assertIn("B1", called)
            self.assertNotIn("这次没有运行", called)
            self.assertNotIn("请先确认设计案例", called)
            self.ran.assert_called_once()
            saved = json.loads((path.parent / "analysis_result.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["members"][0]["forces"]["Mz"], -2.5)
            self.assertEqual(saved["check_status"], "passed")
            self.assertIn("设计合格", called)
            self.assertIn("OCT165x2.0", called)
            design = json.loads((path.parent / "section_design.json").read_text(encoding="utf-8"))
            self.assertEqual(design["members"][0]["governing"], "LRFD1")

    def test_existing_files_can_be_called_without_calculating_again(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "design_case.json"
            case = _ready_case()
            path.write_text(json.dumps(case, ensure_ascii=False), encoding="utf-8")
            answer_sap_request(
                path.read_text(encoding="utf-8"),
                "甲项目",
                [{"role": "user", "content": "调用SAP2000"}],
                path,
            )
            before = (path.parent / "loads.json").read_text(encoding="utf-8")
            reply, _wrote, show, dialog = answer_sap_request(
                path.read_text(encoding="utf-8"),
                "甲项目",
                [{"role": "user", "content": "调用SAP2000"}],
                path,
            )
            self.assertFalse(show)
            self.assertTrue(dialog)
            self.assertNotIn("SAP2000.exe", reply)
            self.assertEqual((path.parent / "loads.json").read_text(encoding="utf-8"), before)
            called, _wrote, called_show, called_dialog = answer_sap_request(
                path.read_text(encoding="utf-8"),
                "甲项目",
                [{"role": "user", "content": "调用SAP2000"}],
                path,
                True,
            )
            self.assertFalse(called_show)
            self.assertFalse(called_dialog)
            self.assertIn("已用 SAP2000 完成计算", called)
            self.assertIn("SAP2000.exe", called)
            self.ran.assert_called_once()
            self.assertEqual((path.parent / "loads.json").read_text(encoding="utf-8"), before)

    def test_changed_arrangement_rebuilds_the_old_line_model(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "design_case.json"
            case = _ready_case()
            path.write_text(json.dumps(case, ensure_ascii=False), encoding="utf-8")
            answer_sap_request(
                path.read_text(encoding="utf-8"),
                "甲项目",
                [{"role": "user", "content": "调用SAP2000"}],
                path,
            )
            case["geometry"]["arrangement_columns"] = "11/22"
            path.write_text(json.dumps(case, ensure_ascii=False), encoding="utf-8")
            reply, wrote, show, dialog = answer_sap_request(
                path.read_text(encoding="utf-8"),
                "甲项目",
                [{"role": "user", "content": "调用SAP2000"}],
                path,
            )
            self.assertTrue(wrote)
            self.assertTrue(show)
            self.assertTrue(dialog)
            self.assertIn("点击确认之后才调用 SAP2000", reply)
            saved = json.loads((path.parent / "line_model.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["arrangement_columns"], "11/22")
            self.assertIn("11 *", reply)

    def test_draft_case_can_be_sent_after_the_dialog(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "design_case.json"
            case = _ready_case()
            case["status"] = "draft"
            path.write_text(json.dumps(case, ensure_ascii=False), encoding="utf-8")
            answer_sap_request(
                path.read_text(encoding="utf-8"),
                "甲项目",
                [{"role": "user", "content": "调用SAP2000"}],
                path,
            )
            reply, _wrote, _show, dialog = answer_sap_request(
                path.read_text(encoding="utf-8"),
                "甲项目",
                [{"role": "user", "content": "调用SAP2000"}],
                path,
            )
            self.assertTrue(dialog)
            self.assertNotIn("请先确认设计案例", reply)
            self.assertNotIn("SAP2000.exe", reply)
            called, _called_wrote, _called_show, called_dialog = answer_sap_request(
                path.read_text(encoding="utf-8"),
                "甲项目",
                [{"role": "user", "content": "调用SAP2000"}],
                path,
                True,
            )
            self.assertFalse(called_dialog)
            self.assertIn("已用 SAP2000 完成计算", called)
            self.assertIn("SAP2000.exe", called)
            self.assertNotIn("请先确认设计案例", called)
            self.ran.assert_called_once()
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["status"], "draft")
