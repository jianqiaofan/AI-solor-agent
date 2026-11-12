"""把对话里确认过的计算参数写回 design_case.json。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from agent.settings import ROOT

_SCHEMA = ROOT / "contracts" / "schemas" / "design_case.schema.json"
_SOURCE = "用户在对话中填写"

_LABELS = {
    "site.wind_speed_averaging": "风速时距",
    "site.terrain_category": "地形类别",
    "site.snow_exposure": "雪荷载暴露条件",
    "site.wind_speed": "风速",
    "site.wind_speed_unit": "风速单位",
    "site.snow_load": "雪荷载",
    "site.snow_load_unit": "雪荷载单位",
    "site.risk_category": "风险类别",
    "geometry.module_length_mm": "组件长度",
    "geometry.module_width_mm": "组件宽度",
    "geometry.ground_clearance_mm": "组件下沿离地高度",
    "geometry.arrangement_rows": "组件排数",
    "geometry.arrangement_columns": "布置列数",
    "geometry.pile_embedment_depth_mm": "桩入土深度",
    "site.temperature_high_c": "极端最高温度",
    "site.temperature_low_c": "极端最低温度",
    "geometry.module_orientation": "组件朝向",
}
_FIXED_UNITS = {
    "geometry.module_length_mm": "mm",
    "geometry.module_width_mm": "mm",
    "geometry.ground_clearance_mm": "mm",
    "geometry.pile_embedment_depth_mm": "mm",
    "site.temperature_high_c": "°C",
    "site.temperature_low_c": "°C",
}


def persist_updates(
    case: dict[str, Any],
    updates: dict[str, Any],
    path: Path | None,
    relative: str,
) -> tuple[bool, bool, str]:
    """返回 (是否有改动, 是否已写入, 给用户看的说明)。校验失败时原文件不动。"""
    if not updates:
        return False, False, ""
    trial = json.loads(json.dumps(case))
    changes = apply_updates(trial, updates)
    if not changes:
        return False, False, ""
    if path is None:
        _replace(case, trial)
        return True, False, ""
    try:
        write_case(path, trial)
    except ValueError as exc:
        return True, False, f"没有写入 {relative}：{exc}"
    _replace(case, trial)
    detail = "；".join(
        f"{_LABELS.get(key, key)} {_show(old)} → {_show(new)}" for key, old, new in changes
    )
    return True, True, f"已写入 {relative}：{detail}。"


def apply_updates(case: dict[str, Any], updates: dict[str, Any]) -> list[tuple[str, Any, Any]]:
    changes: list[tuple[str, Any, Any]] = []
    for key, value in updates.items():
        old = lookup(case, key)
        if old == value:
            continue
        assign(case, key, value)
        changes.append((key, old, value))
    for key, _old, value in changes:
        _upsert_parameter(case, key, value, _unit_for(case, key))
    _refresh_load_units(case, changes)
    return changes


def write_case(path: Path, case: dict[str, Any]) -> None:
    schema = json.loads(_SCHEMA.read_text(encoding="utf-8"))
    try:
        Draft202012Validator(schema).validate(case)
    except ValidationError as exc:
        location = ".".join(str(part) for part in exc.absolute_path) or "design_case"
        raise ValueError(f"{location}：{exc.message}") from exc
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(case, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def assign(target: dict[str, Any], dotted: str, value: Any) -> None:
    parts = dotted.split(".")
    cursor = target
    for part in parts[:-1]:
        child = cursor.get(part)
        if not isinstance(child, dict):
            child = {}
            cursor[part] = child
        cursor = child
    cursor[parts[-1]] = value


def lookup(target: dict[str, Any], dotted: str) -> Any:
    cursor: Any = target
    for part in dotted.split("."):
        if not isinstance(cursor, dict) or part not in cursor:
            return None
        cursor = cursor[part]
    return cursor


def _replace(case: dict[str, Any], trial: dict[str, Any]) -> None:
    case.clear()
    case.update(trial)


def _show(value: Any) -> str:
    if value is None or value == "":
        return "空"
    return str(value)


def _unit_for(case: dict[str, Any], key: str) -> str:
    if key == "site.wind_speed":
        unit = lookup(case, "site.wind_speed_unit")
        return unit if isinstance(unit, str) else ""
    if key == "site.snow_load":
        unit = lookup(case, "site.snow_load_unit")
        return unit if isinstance(unit, str) else ""
    return _FIXED_UNITS.get(key, "")


def _refresh_load_units(case: dict[str, Any], changes: list[tuple[str, Any, Any]]) -> None:
    changed = {key for key, _old, _new in changes}
    if "site.wind_speed_unit" in changed:
        speed = lookup(case, "site.wind_speed")
        if speed is not None:
            _upsert_parameter(case, "site.wind_speed", speed, _unit_for(case, "site.wind_speed"))
    if "site.snow_load_unit" in changed:
        snow = lookup(case, "site.snow_load")
        if snow is not None:
            _upsert_parameter(case, "site.snow_load", snow, _unit_for(case, "site.snow_load"))


def _upsert_parameter(case: dict[str, Any], name: str, value: Any, unit: str) -> None:
    parameters = case.get("parameters")
    if not isinstance(parameters, list):
        parameters = []
        case["parameters"] = parameters
    for item in parameters:
        if isinstance(item, dict) and item.get("name") == name:
            item["value"] = value
            item["unit"] = unit
            item["status"] = "confirmed"
            item["source"] = _SOURCE
            return
    parameters.append(
        {
            "name": name,
            "value": value,
            "unit": unit,
            "status": "confirmed",
            "source": _SOURCE,
        }
    )
