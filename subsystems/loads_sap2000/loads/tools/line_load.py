"""把组件面荷载转成主梁上的线荷载。

组件长度方向的中线与主梁轴线对齐。
主梁每沿轴线 1 m，承受的就是这一米组件长度上的面荷载，所以线荷载等于面荷载乘以组件长度。
"""

from __future__ import annotations

import re
from typing import Any

_AREA_UNITS = {"kN/m2", "kN/m²"}
# 速度风压还不是作用在组件面上的荷载。
_VELOCITY_PREFIXES = ("W_QH_", "W_QP_")
_TILT = re.compile(r"W_(\d+)_")


def is_module_area_load(item: dict[str, Any]) -> bool:
    if str(item.get("unit") or "") not in _AREA_UNITS:
        return False
    return not str(item.get("id") or "").startswith(_VELOCITY_PREFIXES)


def line_intensity(area_kn_m2: float, length_mm: float) -> float:
    """面荷载 kN/m² × 组件长度 m = 线荷载 kN/m。"""
    if length_mm <= 0:
        raise ValueError("组件长度必须大于 0。")
    return float(area_kn_m2) * (float(length_mm) / 1000.0)


def beam_line_cases(
    area_cases: list[dict[str, Any]],
    length_mm: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """每个组件面荷载对应一条主梁线荷载，并留下换算过程。"""
    length_m = length_mm / 1000.0
    cases: list[dict[str, Any]] = []
    trace: list[dict[str, Any]] = []
    for item in area_cases:
        if not is_module_area_load(item):
            continue
        pressure = float(item["value"])
        value = round(line_intensity(pressure, length_mm), 4)
        case_id = str(item["id"])
        cases.append(
            {
                "id": f"{case_id}_LINE",
                "name": f"{item['name']}线荷载",
                "target": "beam",
                "value": value,
                "unit": "kN/m",
                "formula_id": "line.module",
            }
        )
        trace.append(
            {
                "formula_id": "line.module",
                "clause": "组件长度方向的中线与主梁轴线对齐，线荷载等于面荷载乘以组件长度",
                "expression": "w = p·L",
                "substitution": f"{pressure}×{length_m:g} = {value}",
                "result": value,
                "unit": "kN/m",
            }
        )
    return cases, trace


def summary_lines(area_cases: list[dict[str, Any]], length_mm: float) -> list[str]:
    """给确认用的线荷载摘要。风压只保留每个倾角的最大正值和最大负值。"""
    length_m = length_mm / 1000.0
    direct: list[tuple[str, float]] = []
    wind: dict[int, list[float]] = {}
    for item in area_cases:
        if not is_module_area_load(item):
            continue
        value = round(line_intensity(float(item["value"]), length_mm), 4)
        case_id = str(item.get("id") or "")
        tilt = _tilt_of(case_id)
        if tilt is None:
            direct.append((str(item["name"]), value))
            continue
        wind.setdefault(tilt, []).append(value)
    if not direct and not wind:
        return []
    rows = [(name, f"{value} kN/m") for name, value in direct]
    for tilt in sorted(wind):
        values = wind[tilt]
        positive = [item for item in values if item > 0]
        negative = [item for item in values if item < 0]
        if positive:
            rows.append((f"板面风压（{tilt}°，最大正风压）", f"{max(positive)} kN/m"))
        if negative:
            rows.append((f"板面风压（{tilt}°，最大负风压）", f"{min(negative)} kN/m"))
    return [
        f"主梁线荷载 = 面荷载 × 组件长度 {length_m:g} m。"
        "组件长度方向的中线与主梁轴线对齐。",
        "",
        *_markdown_table(("项目", "线荷载"), rows),
    ]


def _markdown_table(headers: tuple[str, str], rows: list[tuple[str, str]]) -> list[str]:
    def line(cells: tuple[str, ...]) -> str:
        return "| " + " | ".join(str(item).replace("|", "/").replace("\n", " ") for item in cells) + " |"

    return [line(headers), line(("---", "---:")), *(line(row) for row in rows)]


def _tilt_of(case_id: str) -> int | None:
    if not case_id.startswith("W_"):
        return None
    found = _TILT.match(case_id)
    if not found:
        return None
    return int(found.group(1))
