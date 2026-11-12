"""调用 SAP2000 之前，先核对荷载和线模。

已有计算结果、用户又不是要求重算时，直接展示那次结果。
两样都还没有时，先按已有规则计算，再请用户确认。
条件不够就指出缺哪一项，不补一个数。
确认之前不调用 SAP2000。
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from agent.activity import SAP_RUNNING, report_activity
from agent.beam_layout import layout_view
from agent.intent import LOADS, SAP
from agent.line_model import answer_line_model
from agent.load_check import answer_load_request, collect_updates
from agent.settings import ROOT

_ASKS_MEANING = re.compile(
    r"(什么是|啥是|何谓|含义|意思).{0,12}(SAP\s*2000|内力|应力比|力学)"
    r"|(SAP\s*2000|内力|应力比).{0,12}(什么意思|含义)",
    re.IGNORECASE,
)
_WANTS_SAP = re.compile(r"SAP\s*2000|结构计算|计算内力|算内力", re.IGNORECASE)
_WANTS_RESULTS = re.compile(
    r"(查看|看看|看一下|看下|展示|显示|列出|给我看).{0,24}(计算结果|计算的结果|应力比|内力|力学)"
    r"|应力比|力学(计算)?结果|结构计算结果|内力结果"
)
_WANTS_RECALC = re.compile(
    r"重新\s*(进行\s*)?(力学\s*)?(计算|算|调用|跑|运行|分析)"
    r"|再\s*(算|计算|调用|跑|运行)(?:\s*(一次|一遍))?"
    r"|重算"
)
_STRUCTURAL = re.compile(r"力学|结构|内力|应力|SAP", re.IGNORECASE)
_CONFIRM = re.compile(r"确认|可以调用|开始调用|调用吧|同意")
_ARRANGEMENT = re.compile(r"布置列数")
_LINE_KEYS = {
    "geometry.module_length_mm",
    "geometry.module_width_mm",
    "geometry.ground_clearance_mm",
    "geometry.arrangement_columns",
}
_BLOCKED = "还不能调用 SAP2000。"
_HOLD = "点击确认之后才调用 SAP2000。"


def wants_sap(text: str) -> bool:
    if _ASKS_MEANING.search(text):
        return False
    return _WANTS_SAP.search(text) is not None


def wants_saved_results(text: str) -> bool:
    """这句话是在看已有的力学或结构计算结果。"""
    if _ASKS_MEANING.search(text):
        return False
    return _WANTS_RESULTS.search(text) is not None


def wants_recalculate(text: str) -> bool:
    """用户明确要求重新做力学计算。"""
    if _ASKS_MEANING.search(text):
        return False
    return _WANTS_RECALC.search(text) is not None


def resolve_sap_intent(intent: str, text: str, messages: list[dict]) -> str:
    """点名 SAP2000、结构计算、内力，或要看已有结果时进入 SAP。上一句还在等参数或等确认时，接着做。"""
    if wants_sap(text) or wants_saved_results(text) or _explicit_structural_recalc(text):
        return SAP
    previous = _previous_assistant(messages)
    if previous.startswith(_BLOCKED) and (_supplies(text) or intent == SAP):
        return SAP
    if _HOLD in previous and (_confirms(text) or _supplies(text) or intent == SAP):
        return SAP
    if intent == SAP:
        return SAP
    return intent


def answer_sap_request(
    case_text: str | None,
    project_name: str,
    messages: list[dict],
    path: Path | None = None,
    confirmed: bool = False,
) -> tuple[str, bool, bool, bool]:
    """返回 (说明, 是否写入了文件, 是否可以打开布置图, 是否要弹出确认对话框)。"""
    latest = _latest_user(messages)
    reading = not confirmed and not wants_recalculate(latest) and not _confirming(messages)
    if reading:
        saved = _saved_report(path, case_text)
        if saved is not None:
            return saved, False, False, False
    note_missing = reading and wants_saved_results(latest)
    reply, wrote, show, dialog = _answer_new_sap(case_text, project_name, messages, path, confirmed)
    if note_missing:
        lead = "已有的 SAP2000 结果读不出来。" if _result_exists(path) else "还没有 SAP2000 计算结果。"
        reply = f"{lead}\n{reply}"
    return reply, wrote, show, dialog


def _answer_new_sap(
    case_text: str | None,
    project_name: str,
    messages: list[dict],
    path: Path | None,
    confirmed: bool,
) -> tuple[str, bool, bool, bool]:
    latest = _latest_user(messages)
    updates = collect_updates(latest)
    line_path = None if path is None else path.parent / "line_model.json"
    loads_path = None if path is None else path.parent / "loads.json"
    need_line = not _line_current(case_text, line_path) or _touches_line(latest, updates)
    need_loads = not _loads_ready(loads_path) or bool(updates)
    if need_line or need_loads:
        return _prepare(case_text, project_name, messages, path, need_line, need_loads)
    if not confirmed:
        return "线模和荷载已经齐备。请在对话框里点击确认。点击确认之后才调用 SAP2000。", False, False, True
    text, wrote = _call(case_text, path)
    return text, wrote, False, False


def _prepare(
    case_text: str | None,
    project_name: str,
    messages: list[dict],
    path: Path | None,
    need_line: bool,
    need_loads: bool,
) -> tuple[str, bool, bool, bool]:
    before = _snapshot(path)
    blocks: list[str] = []
    wrote = False
    show = False
    blocked = False
    if need_line:
        reply, line_wrote, show = answer_line_model(case_text, project_name, messages, path)
        wrote = wrote or line_wrote
        blocks.append(reply)
        if not _line_ready(None if path is None else path.parent / "line_model.json"):
            blocked = True
        case_text = _reread(path, case_text)
    if need_loads:
        reply, load_wrote = answer_load_request(LOADS, case_text, project_name, messages, path)
        wrote = wrote or load_wrote
        blocks.append(reply)
        if not _loads_ready(None if path is None else path.parent / "loads.json"):
            blocked = True
    wrote = wrote or _snapshot(path) != before
    text = "\n\n".join(block for block in blocks if block).strip()
    if blocked:
        return f"{_BLOCKED}\n{text}", wrote, show, False
    return (
        f"{text}\n\n线模和荷载已经齐备。请在对话框里点击确认。点击确认之后才调用 SAP2000。",
        wrote,
        show,
        True,
    )


def _call(case_text: str | None, path: Path | None) -> tuple[str, bool]:
    if not case_text:
        return f"{_BLOCKED}\n还没有设计案例。请先从资料里提取设计参数。", False
    try:
        case = json.loads(case_text)
    except json.JSONDecodeError:
        return f"{_BLOCKED}\n设计案例读不出来。", False
    if not isinstance(case, dict):
        return f"{_BLOCKED}\n设计案例读不出来。", False
    loads_path = None if path is None else path.parent / "loads.json"
    try:
        loads = json.loads(loads_path.read_text(encoding="utf-8")) if loads_path else None
    except (OSError, json.JSONDecodeError):
        return f"{_BLOCKED}\n荷载文件读不出来。", False
    if not isinstance(loads, dict):
        return f"{_BLOCKED}\n荷载文件读不出来。", False
    package_root = ROOT / "subsystems" / "loads_sap2000"
    if str(package_root) not in sys.path:
        sys.path.insert(0, str(package_root))
    from sap2000.model import report
    from sap2000.program import sap2000_executable
    from sap2000.runner import run_design

    try:
        program = sap2000_executable()
    except FileNotFoundError as exc:
        return str(exc), False
    work_dir = path.parent / "SAP2000" if path is not None else package_root / "sap2000" / "templates"
    try:
        work_dir.mkdir(parents=True, exist_ok=True)
        report_activity(SAP_RUNNING)
        result, design = run_design(case, loads, work_dir)
    except Exception as exc:
        return f"SAP2000 没有完成计算。{exc}", False
    if path is not None:
        for name, document in (("analysis_result.json", result), ("section_design.json", design)):
            destination = path.parent / name
            destination.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    return report(result, str(program), design), True


def _explicit_structural_recalc(text: str) -> bool:
    """重新计算风或雪时不要改道到 SAP。没点明力学、结构、内力、应力或 SAP 时，也不改道。"""
    if not wants_recalculate(text):
        return False
    if not _STRUCTURAL.search(text):
        return False
    if re.search(r"风|雪", text) and "荷载" in text:
        return False
    return True


def _confirming(messages: list[dict]) -> bool:
    """上一句正在等确认，而这句是在确认，就继续去调用，不要改成展示旧结果。"""
    if _HOLD not in _previous_assistant(messages):
        return False
    return _confirms(_latest_user(messages))


def _result_exists(path: Path | None) -> bool:
    return path is not None and (path.parent / "analysis_result.json").is_file()


def _saved_report(path: Path | None, case_text: str | None) -> str | None:
    """读得出现成的分析结果时，返回带计算时间的说明。读不出来时返回 None。"""
    if path is None:
        return None
    result_path = path.parent / "analysis_result.json"
    design_path = path.parent / "section_design.json"
    result = _read_json(result_path)
    design = _read_json(design_path)
    if not isinstance(result, dict) or not isinstance(design, dict):
        return None
    members = result.get("members")
    if not isinstance(members, list) or not members:
        return None
    if not isinstance(design.get("members"), list) or not design.get("members"):
        return None
    try:
        stamp = datetime.fromtimestamp(result_path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
    except OSError:
        return None
    package_root = ROOT / "subsystems" / "loads_sap2000"
    if str(package_root) not in sys.path:
        sys.path.insert(0, str(package_root))
    from sap2000.model import report

    try:
        body = report(result, "SAP2000", design)
    except (KeyError, TypeError, ValueError):
        return None
    lines = [
        f"已有 SAP2000 计算结果，计算时间是 {stamp}。这次没有重新调用 SAP2000。",
    ]
    line_path = path.parent / "line_model.json"
    if not _line_current(case_text, line_path) or _loads_newer(path, result_path):
        lines.append("线模或荷载在这次计算之后有改动。要按新的输入重算，请说明重新计算。")
    lines.extend(["", body])
    return "\n".join(lines)


def _loads_newer(case_path: Path, result_path: Path) -> bool:
    loads = case_path.parent / "loads.json"
    try:
        return loads.stat().st_mtime > result_path.stat().st_mtime + 1
    except OSError:
        return False


def _line_current(case_text: str | None, line_path: Path | None) -> bool:
    """已有线模还和当前设计案例的几何一致，才不必重算。"""
    if not _line_ready(line_path) or not case_text:
        return False
    try:
        case = json.loads(case_text)
    except json.JSONDecodeError:
        return False
    geometry = case.get("geometry") if isinstance(case, dict) else None
    if not isinstance(geometry, dict):
        return False
    view = layout_view(geometry)
    if not view.get("ready") or view.get("issues"):
        return False
    saved = _read_json(line_path)
    if str(saved.get("arrangement_columns") or "") != str(geometry.get("arrangement_columns") or "").strip():
        return False
    if abs(float(saved.get("length_mm") or -1) - float(view["length_mm"])) > 0.05:
        return False
    if abs(float(saved.get("h_mm") or -1) - float(view["h_mm"])) > 0.05:
        return False
    old = [float(item["y_mm"]) for item in saved.get("columns") or [] if isinstance(item, dict)]
    fresh = [float(item["y_mm"]) for item in view.get("columns") or []]
    if len(old) != len(fresh):
        return False
    return all(abs(left - right) <= 0.05 for left, right in zip(old, fresh))


def _line_ready(path: Path | None) -> bool:
    data = _read_json(path)
    if not isinstance(data, dict) or data.get("kind") != "line_model":
        return False
    if data.get("issues"):
        return False
    beam = data.get("beam") if isinstance(data.get("beam"), dict) else {}
    columns = data.get("columns")
    return bool(beam.get("start") and beam.get("end") and isinstance(columns, list) and columns)


def _loads_ready(path: Path | None) -> bool:
    data = _read_json(path)
    if not isinstance(data, dict):
        return False
    cases = data.get("cases")
    if not isinstance(cases, list):
        return False
    ids = {str(item.get("id") or "") for item in cases if isinstance(item, dict)}
    return "D" in ids and any(item.startswith("W_") for item in ids) and any(item.startswith("S_") for item in ids)


def _touches_line(text: str, updates: dict[str, Any]) -> bool:
    return bool(_ARRANGEMENT.search(text) or (set(updates) & _LINE_KEYS))


def _supplies(text: str) -> bool:
    return bool(collect_updates(text) or _ARRANGEMENT.search(text))


def _confirms(text: str) -> bool:
    if _supplies(text):
        return False
    return _CONFIRM.search(text) is not None


def _read_json(path: Path | None) -> Any:
    if path is None:
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _reread(path: Path | None, fallback: str | None) -> str | None:
    if path is None:
        return fallback
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return fallback


def _snapshot(path: Path | None) -> tuple[bytes | None, bytes | None, bytes | None]:
    if path is None:
        return None, None, None
    return _bytes(path), _bytes(path.parent / "loads.json"), _bytes(path.parent / "line_model.json")


def _bytes(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except OSError:
        return None


def _latest_user(messages: list[dict]) -> str:
    for item in reversed(messages):
        if item.get("role") == "user":
            return str(item.get("content") or "")
    return ""


def _previous_assistant(messages: list[dict]) -> str:
    seen_user = False
    for item in reversed(messages):
        if item.get("role") == "user" and not seen_user:
            seen_user = True
            continue
        if seen_user and item.get("role") == "assistant":
            return str(item.get("content") or "")
    return ""
