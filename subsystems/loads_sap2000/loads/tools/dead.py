"""组件自重面荷载。

只计组件自重，不含支架。竖向重量除以组件面积，与倾角、朝向无关。
"""

from typing import Any

from loads.tools.records import load_case, need, trace_step
from loads.tools.units import STANDARD_GRAVITY

FORMULA_ID = "dead.module"


def module_area_m2(length_mm: float, width_mm: float) -> float:
    if length_mm <= 0 or width_mm <= 0:
        raise ValueError("组件平面尺寸必须大于 0。")
    return (length_mm / 1000.0) * (width_mm / 1000.0)


def dead_pressure(weight_kg: float, length_mm: float, width_mm: float) -> float:
    """组件自重面荷载，kN/m²。"""
    if weight_kg < 0:
        raise ValueError("组件重量不能为负。")
    area = module_area_m2(length_mm, width_mm)
    return weight_kg * STANDARD_GRAVITY / 1000.0 / area


def build(design_case: dict[str, Any], trace: list[dict[str, Any]]) -> list[dict[str, Any]]:
    geometry = design_case.get("geometry") or {}
    weight = float(need(geometry, "module_weight_kg", label="组件重量"))
    length = float(need(geometry, "module_length_mm", label="组件长度"))
    width = float(need(geometry, "module_width_mm", label="组件宽度"))
    area = module_area_m2(length, width)
    pressure = round(dead_pressure(weight, length, width), 4)
    trace_step(
        trace,
        FORMULA_ID,
        "组件自重除以组件面积",
        "D = m·g / (L·W)",
        f"{weight}×{STANDARD_GRAVITY}/1000/({length / 1000:.4f}×{width / 1000:.4f}) = {pressure}",
        pressure,
        "kN/m2",
    )
    return [
        load_case("D", "组件自重", pressure, "kN/m2", FORMULA_ID),
    ]
