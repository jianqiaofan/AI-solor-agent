"""算风、雪之前，先核对当前项目 design_case.json 里的计算参数。"""

from __future__ import annotations

import json
import re
from typing import Any

from pathlib import Path

from agent.case_edit import persist_updates
from agent.intent import CHAT, EXTRACT, LOADS, SNOW, UPDATE, WIND
from agent.load_tools import run_load_tool

_ASCE = "USA(ASCE7-16)"
_EN = "Europe(Eurocode 1991-4)"
_SUPPORTED = {_ASCE, _EN}
_ASCE_AVERAGING = "3 s gust"
_EN_AVERAGING = "10 min mean"

_AVERAGING = (
    ("10 min mean", ("10 min mean", "10min", "10 min", "10分钟平均", "10分钟", "10 分钟", "十分钟平均", "十分钟")),
    ("3 s gust", ("3 s gust", "3s gust", "3秒阵风", "3秒", "3 秒", "三秒")),
    ("1 h mean", ("1 h mean", "1h mean", "1小时", "1 小时")),
    ("fastest-mile", ("fastest-mile", "fastest mile")),
)
_TERRAIN = re.compile(
    r"(?:地形类别|地形|terrain(?:\s*category)?)"
    r"\s*(?:改成|改为|调成|调为|设为|是|为|[:：])?\s*(0|IV|III|II|I)(?![A-Za-z0-9])",
    re.IGNORECASE,
)
_EXPOSURE = (
    ("windswept", ("windswept", "全暴露")),
    ("sheltered", ("sheltered", "遮蔽")),
    ("normal", ("normal", "正常暴露", "暴露正常", "暴露条件正常")),
)
_EXPOSURE_LABELED = re.compile(
    r"(?:雪荷载暴露条件|暴露条件|雪荷载暴露)"
    r"\s*(?:改成|改为|调成|调为|设为|是|为|[:：])?\s*(windswept|sheltered|normal|全暴露|遮蔽|正常)",
    re.IGNORECASE,
)
_VALUE_INTRO = r"\s*(?:改成|改为|调成|调为|设为|是|为|[:：])?\s*"
_SPEED = re.compile(rf"风速(?!时距){_VALUE_INTRO}([0-9]+(?:\.[0-9]+)?)\s*(m/s|km/h|mph)?", re.IGNORECASE)
_SPEED_UNIT = re.compile(rf"风速单位{_VALUE_INTRO}(m/s|km/h|mph)", re.IGNORECASE)
_SNOW_LOAD = re.compile(
    rf"雪荷载(?!暴露|单位){_VALUE_INTRO}([0-9]+(?:\.[0-9]+)?)\s*(KN/m2|kN/m2|kN/m²|psf)?",
    re.IGNORECASE,
)
_SNOW_UNIT = re.compile(rf"雪荷载单位{_VALUE_INTRO}(KN/m2|kN/m2|kN/m²|psf)", re.IGNORECASE)
_RISK = re.compile(rf"风险类别{_VALUE_INTRO}(IV|III|II|I)(?![A-Za-z0-9])", re.IGNORECASE)
_LENGTH = re.compile(rf"组件长度{_VALUE_INTRO}([0-9]+(?:\.[0-9]+)?)")
_WIDTH = re.compile(rf"组件宽度{_VALUE_INTRO}([0-9]+(?:\.[0-9]+)?)")
_CLEARANCE = re.compile(rf"(?:组件下沿离地高度|离地高度){_VALUE_INTRO}([0-9]+(?:\.[0-9]+)?)")
_ROWS = re.compile(rf"(?:组件排数|排数){_VALUE_INTRO}([0-9]+(?:\.[0-9]+)?)")
_PILE = re.compile(rf"桩入土深度{_VALUE_INTRO}([0-9]+(?:\.[0-9]+)?)")
_TEMP_HIGH = re.compile(rf"(?:极端)?最高温度{_VALUE_INTRO}(-?[0-9]+(?:\.[0-9]+)?)")
_TEMP_LOW = re.compile(rf"(?:极端)?最低温度{_VALUE_INTRO}(-?[0-9]+(?:\.[0-9]+)?)")
_ORIENTATION = re.compile(
    rf"(?:组件朝向|朝向){_VALUE_INTRO}(竖排|竖放|横排|横放|portrait|landscape)",
    re.IGNORECASE,
)
_ORIENTATION_VALUE = {
    "竖排": "Portrait",
    "竖放": "Portrait",
    "portrait": "Portrait",
    "横排": "Landscape",
    "横放": "Landscape",
    "landscape": "Landscape",
}
_LABELED_EXPOSURE = {
    "windswept": "windswept",
    "sheltered": "sheltered",
    "normal": "normal",
    "全暴露": "windswept",
    "遮蔽": "sheltered",
    "正常": "normal",
}


def resolve_load_follow_up(intent: str, messages: list[dict]) -> str:
    """上一句在问缺的参数，而这句正在补，就继续算，不要掉回普通对话。"""
    if intent in (WIND, SNOW, LOADS):
        return intent
    previous = _previous_assistant(messages)
    first = previous.splitlines()[0] if previous else ""
    if not first.startswith("还不能计算") or not supplies_load_parameter(_latest_user(messages)):
        return intent
    if first.startswith("还不能计算风荷载和雪荷载"):
        return LOADS
    if first.startswith("还不能计算风荷载"):
        return WIND
    if first.startswith("还不能计算雪荷载"):
        return SNOW
    return intent


def supplies_load_parameter(text: str) -> bool:
    return bool(collect_updates(text))


def resolve_parameter_edit(intent: str, text: str) -> str:
    """没在算荷载，但这句话是在改计算参数，就去写 design_case.json。"""
    if intent in (WIND, SNOW, LOADS, EXTRACT):
        return intent
    if not collect_updates(text):
        # 分类器当成改参数，但这句话对不上已有字段时，交回带历史的对话。
        if intent == UPDATE:
            return CHAT
        return intent
    if _wants_calculation(text):
        return _calculation_intent(text)
    if intent == UPDATE or _wants_edit(text):
        return UPDATE
    return intent


def answer_parameter_update(
    case_text: str | None,
    project_name: str,
    messages: list[dict],
    path: Path | None = None,
) -> tuple[str, bool]:
    relative = _relative(project_name)
    if not case_text:
        return f"还没有 {relative}。没有写入。", False
    try:
        case = json.loads(case_text)
    except json.JSONDecodeError:
        return f"{relative} 读不出来。没有写入。", False
    if not isinstance(case, dict):
        return f"{relative} 读不出来。没有写入。", False
    updates = collect_updates(_latest_user(messages))
    if not updates:
        return (
            "没有识别到要写入的计算参数。"
            "可以说明风速时距、地形类别、雪荷载暴露条件、风速、雪荷载、风险类别、"
            "组件长度、组件宽度、离地高度、桩入土深度、极端温度或组件朝向。"
        ), False
    changed, wrote, message = persist_updates(case, updates, path, relative)
    if message.startswith("没有写入"):
        return message, False
    if not changed:
        return "这些值和文件里已经一样，没有改。", False
    if not wrote:
        return "没有写入。", False
    return message, True


def answer_load_request(
    intent: str,
    case_text: str | None,
    project_name: str,
    messages: list[dict],
    path: Path | None = None,
) -> tuple[str, bool]:
    actions = _actions(intent)
    relative = _relative(project_name)
    if not case_text:
        return f"还没有 {relative}。请先从资料里提取设计参数。没有这份文件，不会计算荷载。", False
    try:
        case = json.loads(case_text)
    except json.JSONDecodeError:
        return f"{relative} 读不出来。没有计算荷载。", False
    if not isinstance(case, dict):
        return f"{relative} 读不出来。没有计算荷载。", False

    code = _code(case)
    if code not in _SUPPORTED:
        shown = code or "空"
        return (
            f"还不能计算。{relative} 里的设计规范是 {shown}。"
            "现在只能算 USA(ASCE7-16) 和 Europe(Eurocode 1991-4)。"
            "请先确认规范。确认之前不会调用荷载工具。"
        ), False

    supplement = _supplement_text(messages)
    _changed, wrote, saved = persist_updates(case, collect_updates(supplement), path, relative)
    gaps, calls = _plan(case, code, actions, supplement)
    blocks: list[str] = []
    if gaps:
        names = "和".join(
            _action_name(item) for item in ("wind", "snow") if item in actions and item in gaps
        )
        lines = [f"还不能计算{names}。已查看 {relative}，下面这些计算参数还没有："]
        for action in ("wind", "snow"):
            for item in gaps.get(action, []):
                lines.append(f"- {item}")
        lines.append("请补充这些参数。补全之前不会调用对应的荷载工具。")
        blocks.append("\n".join(lines))
    results: list[dict[str, Any]] = []
    for name, kwargs in calls:
        payload = run_load_tool(name, kwargs, code)
        if "error" in payload:
            blocks.append(f"{name} 没有算成：{payload['error']}")
            continue
        results.append(payload)
    if results:
        result_lines = [_format_results(results)]
        status = case.get("status")
        if status and status != "confirmed":
            result_lines.append(f"案例状态还是 {status}。")
        blocks.append("\n".join(result_lines))
    if saved:
        blocks.append(saved)
    return "\n\n".join(blocks).strip(), wrote


def _plan(
    case: dict[str, Any],
    code: str,
    actions: set[str],
    supplement: str,
) -> tuple[dict[str, list[str]], list[tuple[str, dict[str, Any]]]]:
    gaps: dict[str, list[str]] = {}
    calls: list[tuple[str, dict[str, Any]]] = []
    if "wind" in actions:
        missing, kwargs = _wind(case, code, supplement)
        if missing:
            gaps["wind"] = missing
        else:
            calls.append((_wind_tool(code), kwargs))
    if "snow" in actions:
        missing, kwargs = _snow(case, code, supplement)
        if missing:
            gaps["snow"] = missing
        else:
            calls.append((_snow_tool(code), kwargs))
    return gaps, calls


def _wind(
    case: dict[str, Any], code: str, supplement: str
) -> tuple[list[str], dict[str, Any]]:
    site = case.get("site") if isinstance(case.get("site"), dict) else {}
    geometry = case.get("geometry") if isinstance(case.get("geometry"), dict) else {}
    missing: list[str] = []
    speed = _number(site, "wind_speed", "风速", missing)
    unit = _text(site, "wind_speed_unit", "风速单位", missing)
    averaging = _averaging(site.get("wind_speed_averaging"), supplement, code, missing)
    length = _number(geometry, "module_length_mm", "组件长度", missing)
    width = _number(geometry, "module_width_mm", "组件宽度", missing)
    clearance = _number(geometry, "ground_clearance_mm", "组件下沿离地高度", missing)
    kwargs: dict[str, Any] = {
        "wind_speed": speed,
        "wind_speed_unit": unit,
        "wind_speed_averaging": averaging,
        "module_length_mm": length,
        "module_width_mm": width,
        "ground_clearance_mm": clearance,
    }
    rows = geometry.get("arrangement_rows")
    if rows is not None:
        kwargs["arrangement_rows"] = rows
    if code == _ASCE:
        altitude = site.get("altitude_m")
        if altitude is not None:
            kwargs["altitude_m"] = altitude
    else:
        terrain = _stored_choice(site.get("terrain_category"), ("0", "I", "II", "III", "IV"))
        terrain = terrain or _parse_terrain(supplement)
        if not terrain:
            missing.append(
                "地形类别不在资料表里。请按 EN 1991-1-4 表 4.1 指定 0、I、II、III 或 IV。"
            )
        else:
            kwargs["terrain_category"] = terrain
    if missing:
        return missing, {}
    return [], kwargs


def _snow(
    case: dict[str, Any], code: str, supplement: str
) -> tuple[list[str], dict[str, Any]]:
    site = case.get("site") if isinstance(case.get("site"), dict) else {}
    geometry = case.get("geometry") if isinstance(case.get("geometry"), dict) else {}
    missing: list[str] = []
    ground = _number(site, "snow_load", "雪荷载", missing)
    unit = _text(site, "snow_load_unit", "雪荷载单位", missing)
    kwargs: dict[str, Any] = {"snow_load": ground, "snow_load_unit": unit}
    if code == _ASCE:
        category = _text(site, "risk_category", "风险类别", missing)
        kwargs["risk_category"] = category
        width = geometry.get("module_width_mm")
        if width is not None:
            kwargs["module_width_mm"] = width
    else:
        exposure = _stored_choice(site.get("snow_exposure"), ("windswept", "normal", "sheltered"))
        exposure = exposure or _parse_exposure(supplement)
        if not exposure:
            missing.append(
                "雪荷载暴露条件不在资料表里。请指定 windswept（四周无遮挡）、normal 或 sheltered。"
            )
        else:
            kwargs["exposure"] = exposure
    if missing:
        return missing, {}
    return [], kwargs


def _averaging(value: Any, supplement: str, code: str, missing: list[str]) -> str | None:
    required = _ASCE_AVERAGING if code == _ASCE else _EN_AVERAGING
    code_name = "ASCE 7-16" if code == _ASCE else "EN 1991-1-4"
    chosen = value if isinstance(value, str) and value.strip() else _parse_averaging(supplement)
    if chosen == required:
        return chosen
    if not chosen:
        missing.append(f"风速时距是空的。{code_name} 要 {required}。请确认资料中的风速是哪一种时距。")
    else:
        missing.append(
            f"风速时距现在是 {chosen}。{code_name} 要 {required}。请确认时距，确认之前不算风荷载。"
        )
    return None


def _number(source: dict[str, Any], key: str, label: str, missing: list[str]) -> float | None:
    value = source.get(key)
    if value is None or value == "":
        missing.append(f"{label}是空的。")
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        missing.append(f"{label}不是数值。")
        return None


def _text(source: dict[str, Any], key: str, label: str, missing: list[str]) -> str | None:
    value = source.get(key)
    if not isinstance(value, str) or not value.strip():
        missing.append(f"{label}是空的。")
        return None
    return value.strip()


def _code(case: dict[str, Any]) -> str | None:
    site = case.get("site") if isinstance(case.get("site"), dict) else {}
    code = site.get("design_code") or case.get("code_pack")
    if isinstance(code, str) and code.strip():
        return code.strip()
    return None


def _actions(intent: str) -> set[str]:
    if intent == WIND:
        return {"wind"}
    if intent == SNOW:
        return {"snow"}
    return {"wind", "snow"}


def _action_name(action: str) -> str:
    return "风荷载" if action == "wind" else "雪荷载"


def _wind_tool(code: str) -> str:
    return "windASCE16" if code == _ASCE else "windEN1991"


def _snow_tool(code: str) -> str:
    return "snowASCE16" if code == _ASCE else "snowEN1991"


def _format_results(results: list[dict[str, Any]]) -> str:
    blocks: list[str] = []
    for result in results:
        title = "风荷载" if result.get("action") == "wind" else "雪荷载"
        lines = [f"{result.get('code')} {title}："]
        cases = result.get("cases") or []
        if result.get("action") == "wind":
            lines.extend(_wind_reply_lines(cases))
        else:
            for case in cases:
                lines.append(f"- {case['name']}：{case['value']} {case['unit']}")
        assumptions = result.get("assumptions") or []
        if assumptions:
            lines.append("计算中采用的规定：")
            lines.extend(f"- {item}" for item in assumptions)
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def _wind_reply_lines(cases: list[dict[str, Any]]) -> list[str]:
    """速度风压照原样列出。每个倾角的板面风压只留最大正值和最大负值。"""
    lines: list[str] = []
    by_tilt: dict[int, list[tuple[float, str]]] = {}
    for case in cases:
        case_id = str(case.get("id") or "")
        if case_id.startswith(("W_QP_", "W_QH_")):
            lines.append(f"- {case['name']}：{case['value']} {case['unit']}")
            continue
        tilt = _tilt_of(case_id)
        if tilt is None:
            lines.append(f"- {case['name']}：{case['value']} {case['unit']}")
            continue
        by_tilt.setdefault(tilt, []).append((float(case["value"]), str(case.get("unit") or "")))
    for tilt in sorted(by_tilt):
        values = by_tilt[tilt]
        unit = values[0][1]
        positive = [value for value, _unit in values if value > 0]
        negative = [value for value, _unit in values if value < 0]
        if positive:
            lines.append(f"- 板面风压（{tilt}°，最大正风压）：{max(positive)} {unit}")
        if negative:
            lines.append(f"- 板面风压（{tilt}°，最大负风压）：{min(negative)} {unit}")
    return lines


def _tilt_of(case_id: str) -> int | None:
    found = re.match(r"W_(\d+)_", case_id)
    if not found:
        return None
    return int(found.group(1))


def _supplement_text(messages: list[dict]) -> str:
    last_question = -1
    for index, item in enumerate(messages):
        if item.get("role") == "assistant" and "还不能计算" in str(item.get("content") or ""):
            last_question = index
    if last_question < 0:
        return _latest_user(messages)
    parts = [
        str(item.get("content") or "")
        for item in messages[last_question + 1 :]
        if item.get("role") == "user"
    ]
    return "\n".join(parts)


def _previous_assistant(messages: list[dict]) -> str:
    seen_user = False
    for item in reversed(messages):
        if item.get("role") == "user" and not seen_user:
            seen_user = True
            continue
        if seen_user and item.get("role") == "assistant":
            return str(item.get("content") or "")
    return ""


def _latest_user(messages: list[dict]) -> str:
    for item in reversed(messages):
        if item.get("role") == "user":
            return str(item.get("content") or "")
    return ""


def _parse_averaging(text: str) -> str | None:
    lowered = text.lower()
    for canonical, aliases in _AVERAGING:
        if any(alias.lower() in lowered for alias in aliases):
            return canonical
    return None


def _parse_terrain(text: str) -> str | None:
    found = _TERRAIN.search(text)
    if not found:
        return None
    token = found.group(1).upper()
    return "0" if token == "0" else token


def _parse_exposure(text: str) -> str | None:
    labeled = _EXPOSURE_LABELED.search(text)
    if labeled:
        return _LABELED_EXPOSURE[labeled.group(1).lower()]
    lowered = text.lower()
    for canonical, aliases in _EXPOSURE:
        if any(alias.lower() in lowered for alias in aliases):
            return canonical
    return None


def collect_updates(text: str) -> dict[str, Any]:
    """只收集这句话里写明的计算参数，不补用户没说的值。"""
    updates: dict[str, Any] = {}
    averaging = _parse_averaging(text)
    if averaging:
        updates["site.wind_speed_averaging"] = averaging
    terrain = _parse_terrain(text)
    if terrain:
        updates["site.terrain_category"] = terrain
    exposure = _parse_exposure(text)
    if exposure:
        updates["site.snow_exposure"] = exposure
    speed = _SPEED.search(text)
    if speed:
        updates["site.wind_speed"] = _number_token(speed.group(1))
        if speed.group(2):
            updates["site.wind_speed_unit"] = speed.group(2)
    speed_unit = _SPEED_UNIT.search(text)
    if speed_unit:
        updates["site.wind_speed_unit"] = speed_unit.group(1)
    snow = _SNOW_LOAD.search(text)
    if snow:
        updates["site.snow_load"] = _number_token(snow.group(1))
        unit = _snow_unit(snow.group(2))
        if unit:
            updates["site.snow_load_unit"] = unit
    snow_unit = _SNOW_UNIT.search(text)
    if snow_unit:
        parsed = _snow_unit(snow_unit.group(1))
        if parsed:
            updates["site.snow_load_unit"] = parsed
    risk = _RISK.search(text)
    if risk:
        updates["site.risk_category"] = risk.group(1).upper()
    length = _LENGTH.search(text)
    if length:
        updates["geometry.module_length_mm"] = _number_token(length.group(1))
    width = _WIDTH.search(text)
    if width:
        updates["geometry.module_width_mm"] = _number_token(width.group(1))
    clearance = _CLEARANCE.search(text)
    if clearance:
        updates["geometry.ground_clearance_mm"] = _number_token(clearance.group(1))
    rows = _ROWS.search(text)
    if rows:
        updates["geometry.arrangement_rows"] = _number_token(rows.group(1))
    pile = _PILE.search(text)
    if pile:
        updates["geometry.pile_embedment_depth_mm"] = _number_token(pile.group(1))
    high = _TEMP_HIGH.search(text)
    if high:
        updates["site.temperature_high_c"] = _number_token(high.group(1))
    low = _TEMP_LOW.search(text)
    if low:
        updates["site.temperature_low_c"] = _number_token(low.group(1))
    orientation = _ORIENTATION.search(text)
    if orientation:
        updates["geometry.module_orientation"] = _ORIENTATION_VALUE[orientation.group(1).lower()]
    return updates


def _relative(project_name: str) -> str:
    if project_name:
        return f"projects/{project_name}/成果/design_case.json"
    return "design_case.json"


def _wants_calculation(text: str) -> bool:
    return any(word in text for word in ("计算", "算一下", "算风", "算雪", "算荷载"))


def _wants_edit(text: str) -> bool:
    return any(word in text for word in ("改", "补", "填", "设为", "调成", "调为", "时距", "地形", "暴露"))


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


def _stored_choice(value: Any, allowed: tuple[str, ...]) -> str | None:
    if not isinstance(value, str):
        return None
    token = value.strip()
    if token in allowed:
        return token
    return None


def _number_token(token: str) -> int | float:
    value = float(token)
    if value.is_integer():
        return int(value)
    return value


def _snow_unit(token: str | None) -> str | None:
    if not token:
        return None
    if token.lower() == "psf":
        return "psf"
    return "KN/m2"
