"""正八角管截面：截面参数和截面表文件。

截面表文件只在第一次时建立。以后只追加表里还没有的厚度，已有的行不重算、不改动。

几何约定：
- 外轮廓是正八边形，对边距离（两条平行边之间）为 across_flats_mm。
- 壁厚 t 垂直于边量取，内轮廓是对边距离 across_flats_mm - 2t 的正八边形。
- 角部按尖角计算，不计折弯圆角。
- 形心在八边形中心。惯性矩对任一形心轴都相同。
- 截面模量分边轴（中和轴平行于一对边）和角轴（中和轴穿过一对角）两种，角轴较小。
- 抗扭惯性矩按薄壁闭口截面 Bredt 公式，以壁厚中线计算。
- 剪切面积取 A/2，与薄壁圆管相同。
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

STEEL_DENSITY_KG_M3 = 7850.0
_TAN = math.tan(math.pi / 8)

Q355B = {
    "name": "Q355B",
    "fy_mpa": 355.0,
    "fy_note": "厚度不超过 16 mm 时的屈服强度",
    "E_mpa": 206000.0,
    "poisson": 0.3,
    "thermal_expansion": 1.2e-5,
    "density_kg_m3": STEEL_DENSITY_KG_M3,
}

UNITS = {
    "length": "mm",
    "area": "mm2",
    "static_moment": "mm3",
    "inertia": "mm4",
    "modulus": "mm3",
    "mass": "kg/m",
}

NOTES = [
    "外轮廓为正八边形，across_flats_mm 是两条平行边之间的距离。",
    "壁厚 t 垂直于边量取，内轮廓是对边距离 across_flats_mm - 2t 的正八边形。",
    "角部按尖角计算，不计折弯圆角。",
    "形心在八边形中心，centroid_from_flat_mm 是形心到外侧边的距离。",
    "static_moment_mm3 是中和轴一侧半个截面对形心轴的面积矩（静矩）。",
    "惯性矩对任一形心轴相同，极惯性矩为其两倍。",
    "截面模量分边轴（中和轴平行于一对边）和角轴（中和轴穿过一对角），角轴较小。",
    "抗扭惯性矩和抗扭截面模量按薄壁闭口截面 Bredt 公式，以壁厚中线计算。",
    "剪切面积取 A/2。",
]


def octagon_tube(across_flats_mm: float, thickness_mm: float) -> dict[str, Any]:
    outer = across_flats_mm / 2.0
    inner = outer - thickness_mm
    if thickness_mm <= 0 or inner <= 0:
        raise ValueError(f"壁厚 {thickness_mm} mm 不适用于对边 {across_flats_mm} mm 的八角管。")
    flat_out, flat_in = _octagon(outer, 0.0), _octagon(inner, 0.0)
    corner_out, corner_in = _octagon(outer, math.pi / 8), _octagon(inner, math.pi / 8)

    area = _area(flat_out) - _area(flat_in)
    inertia = _inertia_x(flat_out) - _inertia_x(flat_in)
    static_flat = _half_moment(flat_out) - _half_moment(flat_in)
    static_corner = _half_moment(corner_out) - _half_moment(corner_in)
    corner_radius = outer / math.cos(math.pi / 8)

    middle = outer - thickness_mm / 2.0
    enclosed = 8.0 * middle**2 * _TAN
    perimeter = 16.0 * middle * _TAN
    torsion = 4.0 * enclosed**2 * thickness_mm / perimeter

    return {
        "name": section_name(across_flats_mm, thickness_mm),
        "t_mm": round(thickness_mm, 2),
        "across_corners_mm": _round(2.0 * corner_radius),
        "side_mm": _round(2.0 * outer * _TAN),
        "area_mm2": _round(area),
        "mass_kg_per_m": round(area * 1e-6 * STEEL_DENSITY_KG_M3, 4),
        "centroid_from_flat_mm": _round(outer),
        "static_moment_mm3": _round(static_flat),
        "static_moment_corner_mm3": _round(static_corner),
        "I_mm4": _round(inertia),
        "polar_moment_mm4": _round(2.0 * inertia),
        "W_el_flat_mm3": _round(inertia / outer),
        "W_el_corner_mm3": _round(inertia / corner_radius),
        "W_pl_flat_mm3": _round(2.0 * static_flat),
        "W_pl_corner_mm3": _round(2.0 * static_corner),
        "radius_of_gyration_mm": _round(math.sqrt(inertia / area)),
        "torsion_constant_mm4": _round(torsion),
        "torsion_modulus_mm3": _round(2.0 * enclosed * thickness_mm),
        "shear_area_mm2": _round(area / 2.0),
    }


def section_name(across_flats_mm: float, thickness_mm: float) -> str:
    return f"OCT{across_flats_mm:g}x{thickness_mm:.1f}"


def thickness_steps(first_mm: float, last_mm: float, step_mm: float) -> list[float]:
    count = int(round((last_mm - first_mm) / step_mm))
    return [round(first_mm + index * step_mm, 2) for index in range(count + 1)]


def add_octagon_sections(
    path: Path,
    across_flats_mm: float,
    thicknesses_mm: list[float],
    material: dict[str, Any] = Q355B,
) -> list[str]:
    """把表里没有的厚度追加进截面表文件，返回新加的截面名称。"""
    path = Path(path)
    if path.exists():
        table = json.loads(path.read_text(encoding="utf-8"))
        if abs(float(table["across_flats_mm"]) - across_flats_mm) > 1e-9:
            raise ValueError(f"{path.name} 的对边距离是 {table['across_flats_mm']} mm，不是 {across_flats_mm} mm。")
        if table["material"]["name"] != material["name"]:
            raise ValueError(f"{path.name} 的材质是 {table['material']['name']}，不是 {material['name']}。")
    else:
        table = {
            "kind": "section_table",
            "family": "正八角管",
            "shape": "regular_octagon_tube",
            "across_flats_mm": across_flats_mm,
            "material": dict(material),
            "units": UNITS,
            "notes": NOTES,
            "sections": [],
        }
    present = {round(float(item["t_mm"]), 2) for item in table["sections"]}
    added: list[str] = []
    for thickness in thicknesses_mm:
        key = round(float(thickness), 2)
        if key in present:
            continue
        row = octagon_tube(across_flats_mm, key)
        table["sections"].append(row)
        present.add(key)
        added.append(row["name"])
    if added or not path.exists():
        table["sections"].sort(key=lambda item: float(item["t_mm"]))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(table, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return added


def load_sections(path: Path) -> dict[str, Any]:
    table = json.loads(Path(path).read_text(encoding="utf-8"))
    if table.get("kind") != "section_table" or not table.get("sections"):
        raise ValueError(f"{Path(path).name} 不是可用的截面表。")
    return table


def _octagon(inradius: float, turn: float) -> list[tuple[float, float]]:
    """逆时针的正八边形顶点。turn 为 0 时有一对边与 x 轴平行。"""
    circumradius = inradius / math.cos(math.pi / 8)
    return [
        (
            circumradius * math.cos(math.pi / 8 + index * math.pi / 4 + turn),
            circumradius * math.sin(math.pi / 8 + index * math.pi / 4 + turn),
        )
        for index in range(8)
    ]


def _area(points: list[tuple[float, float]]) -> float:
    return 0.5 * sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in _edges(points))


def _inertia_x(points: list[tuple[float, float]]) -> float:
    """对 x 轴的惯性矩 ∫y² dA。"""
    return sum(
        (x0 * y1 - x1 * y0) * (y0 * y0 + y0 * y1 + y1 * y1) for (x0, y0), (x1, y1) in _edges(points)
    ) / 12.0


def _half_moment(points: list[tuple[float, float]]) -> float:
    """y ≥ 0 那一半对 x 轴的面积矩 ∫y dA。"""
    upper = _clip_upper(points)
    return sum((x0 * y1 - x1 * y0) * (y0 + y1) for (x0, y0), (x1, y1) in _edges(upper)) / 6.0


def _clip_upper(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    kept: list[tuple[float, float]] = []
    for (x0, y0), (x1, y1) in _edges(points):
        if y0 >= 0:
            kept.append((x0, y0))
        if (y0 >= 0) != (y1 >= 0):
            ratio = y0 / (y0 - y1)
            kept.append((x0 + ratio * (x1 - x0), 0.0))
    return kept


def _edges(points: list[tuple[float, float]]):
    return zip(points, points[1:] + points[:1])


def _round(value: float) -> float:
    return round(value, 3)
