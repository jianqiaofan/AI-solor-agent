"""识别到要设计支架时，只布置主梁和立柱的中心线。

几何用已经实现的立柱布置规则。不选截面，不加荷载，也不运行 SAP2000。
sap2000/skill/SKILL.md 仍是后续建模步骤的位置，这一步不读取它来加截面或荷载。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from agent.activity import LAYOUT_RUNNING, report_activity
from agent.beam_layout import layout_view, parse_counts
from agent.case_edit import persist_updates
from agent.intent import CHAT, DESIGN, EXTRACT, LOADS, SAP, SNOW, UPDATE, WIND
from agent.load_check import collect_updates

_LOAD_INTENTS = (WIND, SNOW, LOADS)
_ARRANGEMENT = re.compile(
    r"布置列数\s*(?:改成|改为|调成|调为|设为|是|为|[:：])?\s*"
    r"([1-9]\d*(?:\s*/\s*[1-9]\d*)*)"
)
_ASKS_MEANING = re.compile(r"(什么是|啥是|何谓|含义|意思).{0,8}(线模|支架)|(线模|支架).{0,8}(什么意思|含义)")
_WANTS_MODEL = re.compile(r"(设计|建立|生成|做|出|布置).{0,8}(支架线模|线模|支架)|支架设计")


def wants_line_model(text: str) -> bool:
    if _ASKS_MEANING.search(text):
        return False
    return _WANTS_MODEL.search(text) is not None


def resolve_design_intent(intent: str, text: str, messages: list[dict]) -> str:
    """设计支架只进入线模。提取和算荷载优先，避免一句话同时命中时改道。"""
    if intent in _LOAD_INTENTS or intent in (EXTRACT, SAP):
        return intent
    if _asks_for_loads(text):
        if wants_line_model(text) or intent == DESIGN:
            return _calculation_intent(text)
        return intent
    if wants_line_model(text) or intent == DESIGN:
        return DESIGN
    if intent in (CHAT, UPDATE) and _continues_design(messages, text):
        return DESIGN
    return intent


def answer_line_model(
    case_text: str | None,
    project_name: str,
    messages: list[dict],
    path: Path | None = None,
) -> tuple[str, bool, bool]:
    """返回 (说明, 是否写入了文件, 是否可以打开布置图)。"""
    relative = _relative(project_name, "design_case.json")
    if not case_text:
        return f"还没有 {relative}。请先从资料里提取设计参数。没有这份文件，不会布置线模。", False, False
    try:
        case = json.loads(case_text)
    except json.JSONDecodeError:
        return f"{relative} 读不出来。没有布置线模。", False, False
    if not isinstance(case, dict):
        return f"{relative} 读不出来。没有布置线模。", False, False

    latest = _latest_user(messages)
    updates = collect_updates(latest)
    arrangement = _arrangement(latest)
    if arrangement:
        updates["geometry.arrangement_columns"] = arrangement
    _changed, wrote, saved = persist_updates(case, updates, path, relative)
    if saved.startswith("没有写入"):
        return saved, False, False

    geometry = case.get("geometry")
    if not isinstance(geometry, dict):
        return _with_saved(saved, "还不能设计支架线模。设计案例里没有几何参数。"), wrote, False
    report_activity(LAYOUT_RUNNING)
    view = layout_view(geometry)
    if not view.get("ready"):
        reason = str(view.get("message") or "几何参数还不够。")
        return _with_saved(saved, f"还不能设计支架线模。{reason}"), wrote, False

    model_path = None if path is None else path.parent / "line_model.json"
    model_relative = _relative(project_name, "line_model.json")
    document = _document(view, geometry)
    if model_path is not None:
        try:
            model_path.parent.mkdir(parents=True, exist_ok=True)
            model_path.write_text(
                json.dumps(document, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        except OSError:
            return _with_saved(saved, "线模没有写成。"), wrote, False
        wrote = True
    return _report(view, geometry, saved, model_relative if model_path is not None else ""), wrote, True


def _continues_design(messages: list[dict], text: str) -> bool:
    previous = _previous_assistant(messages)
    first = previous.splitlines()[0] if previous else ""
    if not first.startswith("还不能设计支架线模"):
        return False
    return bool(collect_updates(text) or _arrangement(text))


def _asks_for_loads(text: str) -> bool:
    return any(word in text for word in ("计算", "算一下", "算风", "算雪", "算荷载"))


def _calculation_intent(text: str) -> str:
    wind = "风" in text
    snow = "雪" in text
    if wind and snow:
        return LOADS
    if snow and not wind:
        return SNOW
    if wind and not snow:
        return WIND
    return LOADS


def _arrangement(text: str) -> str | None:
    found = _ARRANGEMENT.search(text)
    if not found:
        return None
    return re.sub(r"\s+", "", found.group(1))


def _document(view: dict[str, Any], geometry: dict[str, Any]) -> dict[str, Any]:
    height = float(view["h_mm"])
    columns = []
    for column in view["columns"]:
        y_mm = float(column["y_mm"])
        columns.append(
            {
                "index": column["index"],
                "kind": column["kind"],
                "y_mm": y_mm,
                "bottom": [0, y_mm, 0],
                "top": [0, y_mm, height],
            }
        )
    return {
        "kind": "line_model",
        "units": "mm",
        "tilt_angle_deg": 60,
        "arrangement_columns": geometry.get("arrangement_columns"),
        "h_mm": height,
        "length_mm": view["length_mm"],
        "beam": {"start": [0, 0, height], "end": [0, view["length_mm"], height]},
        "columns": columns,
        "issues": list(view.get("issues") or []),
    }


def _report(view: dict[str, Any], geometry: dict[str, Any], saved: str, model_relative: str) -> str:
    height = float(view["h_mm"])
    length = float(view["length_mm"])
    width = float(geometry["module_width_mm"])
    counts = parse_counts(str(geometry.get("arrangement_columns") or "")) or []
    pitch = width + 20
    lines = ["支架线模只包含主梁和立柱的中心线。没有选截面，没有加荷载，也没有运行 SAP2000。"]
    if saved:
        lines.insert(0, saved)
    if model_relative:
        lines.append(f"已写入 {model_relative}。")
    lines.append("倾角按线模规则取 60°。")
    lines.append(
        "h = 0.5 * {length} * cos(60°) + {clearance} = {height} mm".format(
            length=_mm(float(geometry["module_length_mm"])),
            clearance=_mm(float(geometry["ground_clearance_mm"])),
            height=_mm(height),
        )
    )
    segments = [f"{count} * ({_mm(width)} + 20)" for count in counts]
    lines.append(f"L = {' + 500 + '.join(segments)} = {_mm(length)} mm")
    lines.append(f"主梁起点 (0, 0, {_mm(height)}) mm")
    lines.append(f"主梁终点 (0, {_mm(length)}, {_mm(height)}) mm")
    for index in range(1, len(counts)):
        y_mm = sum(counts[:index]) * pitch + (index - 1) * 500 + 250
        terms = [f"({'+'.join(str(count) for count in counts[:index])}) * {_mm(pitch)}"]
        if index > 1:
            terms.append(str((index - 1) * 500))
        terms.append("250")
        lines.append(f"驱动立柱 {index}")
        lines.append(f"y = {' + '.join(terms)} = {_mm(y_mm)} mm")
    lines.append("立柱")
    columns = list(view["columns"])
    for position, column in enumerate(columns):
        y_mm = float(column["y_mm"])
        kind = "驱动" if column["kind"] == "drive" else "非驱动"
        notes = []
        if position == 0:
            notes.append(f"起点侧悬挑 {_mm(y_mm)} mm")
        else:
            gap = y_mm - float(columns[position - 1]["y_mm"])
            notes.append(f"间距 {_mm(gap)} mm，{_multiple(gap)} 100 的整数倍")
        if position == len(columns) - 1:
            notes.append(f"终点侧悬挑 {_mm(length - y_mm)} mm")
        lines.append(
            f"{column['index']}  {kind}  下端 (0, {_mm(y_mm)}, 0) mm  "
            f"上端 (0, {_mm(y_mm)}, {_mm(height)}) mm  " + "，".join(notes)
        )
    issues = list(view.get("issues") or [])
    if issues:
        lines.append("有一段放不下，没有在范围外补立柱。")
        lines.extend(issues)
    return "\n".join(lines)


def _with_saved(saved: str, message: str) -> str:
    if not saved:
        return message
    return saved + "\n" + message


def _multiple(gap: float) -> str:
    if abs(gap / 100 - round(gap / 100)) * 100 <= 0.001:
        return "是"
    return "不是"


def _mm(value: float) -> str:
    if abs(value - round(value)) < 0.05:
        return str(int(round(value)))
    return f"{value:.1f}"


def _relative(project_name: str, filename: str) -> str:
    if project_name:
        return f"projects/{project_name}/成果/{filename}"
    return filename


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
