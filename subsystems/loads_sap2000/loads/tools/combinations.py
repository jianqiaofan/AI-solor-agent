"""ASCE 7-16 第 2.3.1 节强度设计（LRFD）组合。

活荷载 L、屋面活荷载 Lr、雨 R、地震 E 都没有，取 0：
1. 1.4D
2. 1.2D + 0.5S
3. 1.2D + 1.6S，以及 1.2D + 1.6S + 0.5W
4. 1.2D + 1.0W，以及 1.2D + 1.0W + 0.5S
5. 0.9D + 1.0W

每个风工况是一种可能的风况，各自单独组合。雪只在 0° 时积在组件上，
所以雪只和同一倾角的风组合。速度风压不是作用，不进组合。
"""

from __future__ import annotations

import re
from typing import Any

_WIND = re.compile(r"W_(\d+)_.+")
_SNOW = re.compile(r"S_(\d+)")


def strength_combinations(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """cases 里用面荷载编号（D、S_0、W_0_F……）。没有组件自重 D 时返回空表。"""
    ids = [str(item.get("id") or "") for item in cases if isinstance(item, dict)]
    if "D" not in ids:
        return []
    snows = [(item, int(found.group(1))) for item in ids if (found := _SNOW.fullmatch(item))]
    winds = [
        (item, int(found.group(1)))
        for item in ids
        if not item.endswith("_LINE")
        and not item.startswith(("W_QP_", "W_QH_"))
        and (found := _WIND.fullmatch(item))
    ]
    combos = [_combo("LRFD1", [("D", 1.4)])]
    for snow, tilt in snows:
        combos.append(_combo(f"LRFD2_{snow}", [("D", 1.2), (snow, 0.5)]))
        combos.append(_combo(f"LRFD3_{snow}", [("D", 1.2), (snow, 1.6)]))
        for wind, wind_tilt in winds:
            if wind_tilt == tilt:
                combos.append(_combo(f"LRFD3_{snow}_{wind}", [("D", 1.2), (snow, 1.6), (wind, 0.5)]))
    for wind, wind_tilt in winds:
        combos.append(_combo(f"LRFD4_{wind}", [("D", 1.2), (wind, 1.0)]))
        for snow, tilt in snows:
            if wind_tilt == tilt:
                combos.append(_combo(f"LRFD4_{wind}_{snow}", [("D", 1.2), (wind, 1.0), (snow, 0.5)]))
    for wind, _tilt in winds:
        combos.append(_combo(f"LRFD5_{wind}", [("D", 0.9), (wind, 1.0)]))
    return combos


def formula(combo: dict[str, Any]) -> str:
    """把组合写成 1.2D + 1.0W_0_F 这样的式子。"""
    parts = []
    for item in combo.get("factors") or []:
        name = str(item["case_id"]).removesuffix("_LINE")
        parts.append(f"{float(item['factor']):.1f}{name}")
    return " + ".join(parts)


def _combo(combo_id: str, factors: list[tuple[str, float]]) -> dict[str, Any]:
    return {
        "id": combo_id,
        "factors": [{"case_id": case_id, "factor": factor} for case_id, factor in factors],
    }
