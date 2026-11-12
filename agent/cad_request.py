"""生成 CAD 图纸：打开 AutoCAD，把当前线模画成立面并标注尺寸。

线模还没有，或和当前几何不一致时，先按已有规则布置，再画。
这一步不画截面、图框和其他构件。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

from agent.activity import CAD_RUNNING, report_activity
from agent.intent import CAD, CHAT, EXTRACT, LOADS, SAP, SNOW, WIND
from agent.line_model import answer_line_model
from agent.load_check import collect_updates
from agent.sap_request import _line_current, _line_ready, _touches_line
from agent.settings import ROOT

_ASKS_MEANING = re.compile(
    r"(什么是|啥是|何谓|含义|意思).{0,12}(CAD|图纸)|(CAD|图纸).{0,12}(什么意思|含义)",
    re.IGNORECASE,
)
_WANTS_CAD = re.compile(
    r"CAD|出图|(?:生成|画|出|打开|做).{0,8}图纸",
    re.IGNORECASE,
)
_WANTS_SAP = re.compile(r"SAP\s*2000|结构计算|计算内力|算内力", re.IGNORECASE)
_BLOCKED = "还不能生成 CAD 图纸。"
_PACKAGE = ROOT / "subsystems" / "cad"


def wants_cad(text: str) -> bool:
    if _ASKS_MEANING.search(text):
        return False
    return _WANTS_CAD.search(text) is not None


def resolve_cad_intent(intent: str, text: str, messages: list[dict]) -> str:
    """点名 CAD、出图或图纸时去画立面。提取、算荷载和 SAP2000 仍优先。"""
    if _ASKS_MEANING.search(text):
        return CHAT if intent == CAD else intent
    if intent in (EXTRACT, WIND, SNOW, LOADS, SAP) or _WANTS_SAP.search(text):
        return intent
    if any(word in text for word in ("计算", "算一下", "算风", "算雪", "算荷载")):
        return intent
    if wants_cad(text):
        return CAD
    previous = _previous_assistant(messages)
    if previous.startswith(_BLOCKED) and (_supplies(text) or intent == CAD):
        return CAD
    if intent == CAD:
        return CAD
    return intent


def answer_cad_request(
    case_text: str | None,
    project_name: str,
    messages: list[dict],
    path: Path | None = None,
) -> tuple[str, bool, bool]:
    """返回 (说明, 是否写入了文件, 是否可以打开布置图)。"""
    if path is None:
        return "请先选择一个项目，再生成 CAD 图纸。", False, False
    latest = _latest_user(messages)
    updates = collect_updates(latest)
    line_path = path.parent / "line_model.json"
    prepared = ""
    wrote = False
    show = False
    if not _line_current(case_text, line_path) or _touches_line(latest, updates):
        prepared, wrote, show = answer_line_model(case_text, project_name, messages, path)
        if not _line_ready(line_path):
            return _blocked(prepared), wrote, show
    model = _read_json(line_path)
    if not isinstance(model, dict):
        return _blocked(prepared or "线模文件读不出来。"), wrote, show
    destination = path.parent / "CAD" / "line_model.dwg"
    relative = _relative(project_name)
    if str(_PACKAGE) not in sys.path:
        sys.path.insert(0, str(_PACKAGE))
    from cad.session import draw_line_model

    report_activity(CAD_RUNNING)
    try:
        program = draw_line_model(model, destination)
    except Exception as exc:
        return _blocked(prepared, f"CAD 图纸没有画成。{exc}"), wrote, show
    wrote = True
    text = _report(program, relative, model)
    if prepared:
        text = prepared.rstrip() + "\n\n" + text
    return text, wrote, False


def _report(program: Path, relative: str, model: dict[str, Any]) -> str:
    height = float(model["h_mm"])
    length = float(model["length_mm"])
    count = len(model.get("columns") or [])
    return "\n".join(
        [
            f"已打开 AutoCAD，并把线模画成立面：{program}。",
            f"图纸文件：{relative}。",
            "立面里 X 是线模的 Y，Y 是线模的 Z，单位 mm。",
            (
                f"主梁从 (0, {_mm(height)}) 到 ({_mm(length)}, {_mm(height)})，"
                f"立柱 {count} 根。"
            ),
            (
                f"尺寸标了各段间距、两端悬挑、主梁总长 {_mm(length)} mm "
                f"和中心线高度 {_mm(height)} mm。"
            ),
        ]
    )


def _blocked(detail: str, failure: str = "") -> str:
    parts = [_BLOCKED]
    if detail:
        parts.append(detail.strip())
    if failure:
        parts.append(failure)
    return "\n".join(parts)


def _supplies(text: str) -> bool:
    return bool(collect_updates(text))


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _relative(project_name: str) -> str:
    if project_name:
        return f"projects/{project_name}/成果/CAD/line_model.dwg"
    return "CAD/line_model.dwg"


def _mm(value: float) -> str:
    if abs(value - round(value)) < 0.05:
        return str(int(round(value)))
    return f"{value:.1f}"


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
