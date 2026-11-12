"""按截面强度算应力比，并从截面表里挑选截面。

每个输出点、每个工况或组合各算一次，取最大值：
- 正应力 σ = |N| / A + √(M2² + M3²) / W，W 取角轴弹性截面模量（较小的一个）
- 剪应力 τ = √(V2² + V3²) / As + |T| / Wt
- 应力比 = √(σ² + 3τ²) / (φ · fy)，φ = 0.9

只验算截面强度。立柱的整体稳定和板件局部屈曲没有验算。
"""

from __future__ import annotations

import math
from typing import Any

PHI = 0.9
SELECT_LIMIT = 0.95
ACCEPT_LIMIT = 1.0


def station_ratio(row: dict[str, Any], section: dict[str, Any], fy_mpa: float) -> float:
    axial = abs(float(row["P"])) * 1e3 / float(section["area_mm2"])
    moment = math.hypot(float(row["M2"]), float(row["M3"])) * 1e6
    bending = moment / float(section["W_el_corner_mm3"])
    shear = math.hypot(float(row["V2"]), float(row["V3"])) * 1e3 / float(section["shear_area_mm2"])
    twist = abs(float(row["T"])) * 1e6 / float(section["torsion_modulus_mm3"])
    normal = axial + bending
    tangential = shear + twist
    return math.sqrt(normal**2 + 3.0 * tangential**2) / (PHI * fy_mpa)


def member_ratio(
    rows: list[dict[str, Any]],
    section: dict[str, Any],
    fy_mpa: float,
) -> tuple[float, str]:
    """返回最大应力比和控制它的工况或组合。"""
    if not rows:
        raise ValueError("没有内力，不能验算。")
    worst = max(rows, key=lambda row: station_ratio(row, section, fy_mpa))
    return station_ratio(worst, section, fy_mpa), str(worst.get("case") or "")


def lightest_section(
    rows: list[dict[str, Any]],
    sections: list[dict[str, Any]],
    fy_mpa: float,
    limit: float = SELECT_LIMIT,
) -> dict[str, Any] | None:
    """应力比不超过 limit 的截面里，单米重最轻的一个。都不行时返回 None。"""
    for section in sorted(sections, key=lambda item: float(item["mass_kg_per_m"])):
        ratio, _case = member_ratio(rows, section, fy_mpa)
        if ratio <= limit:
            return section
    return None
