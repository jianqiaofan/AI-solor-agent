"""组件风荷载面压，ASCE 7-16 第 26 章。

速度风压按式 26.10-1，风速必须是 3 s 阵风。跟踪支架计算 0° 和 60° 两个倾角。
build() 只写速度风压 qh。0° 的设计风压在 code_loads.windASCE16 里乘图 27.3-4 的 CN。
该图只到 45°，60° 不外推。设计风压的公式是 p = qh·G·CN（第 27.3.2 节）。
"""

import math
from typing import Any

from loads.basis import EXPOSURE_CATEGORY, MODULE_ORIENTATION, WIND_TILTS_DEG
from loads.tools.records import load_case, need, trace_step
from loads.tools.units import (
    FEET_PER_METER,
    KN_PER_M2_PER_PSF,
    METERS_PER_SECOND_PER_MPH,
    to_mps,
)

FORMULA_Q = "wind.qh"
FORMULA_P = "wind.p"
THREE_SECOND = "3 s gust"
# 式 26.10-1 的空气密度系数，V 以 mph 计，结果为 psf。
AIR_DENSITY = 0.00256
# 表 26.6-1，建筑物主抗风体系。
DIRECTIONALITY = 0.85
# 第 26.8 节，没有山丘、山脊或陡坡资料时取 1。
TOPOGRAPHIC = 1.0
# 第 26.11.1 条，刚性结构。
GUST_FACTOR = 0.85
# 第 26.10.1 条，Kz 公式用的 α 和 zg（ft）。
EXPOSURE_PARAMETERS = {
    "B": (7.0, 1200.0),
    "C": (9.5, 900.0),
    "D": (11.5, 700.0),
}
KZ_MINIMUM_FT = 15.0


def velocity_pressure_coefficient(height_ft: float, exposure: str = EXPOSURE_CATEGORY) -> float:
    """Kz，式 26.10-1。z 低于 15 ft 时按 15 ft 计算。"""
    try:
        alpha, gradient_ft = EXPOSURE_PARAMETERS[exposure]
    except KeyError as exc:
        raise ValueError(f"地面粗糙度 {exposure} 不在 B、C、D 之中。") from exc
    if height_ft < 0:
        raise ValueError("计算高度不能为负。")
    z = min(max(height_ft, KZ_MINIMUM_FT), gradient_ft)
    return 2.01 * (z / gradient_ft) ** (2.0 / alpha)


def ground_elevation_factor(elevation_m: float | None) -> float:
    """Ke，式 26.9-1。没有海拔时按规范允许的 1.0。"""
    if elevation_m is None:
        return 1.0
    elevation_ft = elevation_m * FEET_PER_METER
    return math.exp(-0.0000362 * elevation_ft)


def mean_panel_height_m(
    ground_clearance_mm: float,
    slope_length_mm: float,
    tilt_deg: float,
) -> float:
    """组件平面形心离地高度。斜长沿倾斜方向。"""
    clearance_m = ground_clearance_mm / 1000.0
    rise_m = slope_length_mm / 1000.0 * math.sin(math.radians(tilt_deg))
    return clearance_m + 0.5 * rise_m


def velocity_pressure(
    speed: float,
    speed_unit: str,
    averaging: str,
    height_m: float,
    exposure: str = EXPOSURE_CATEGORY,
    elevation_m: float | None = None,
    directionality: float = DIRECTIONALITY,
    topographic: float = TOPOGRAPHIC,
) -> float:
    """速度风压 qh，kN/m²。"""
    if averaging != THREE_SECOND:
        raise ValueError(
            f"式 26.10-1 使用 3 s 阵风。当前时距是 {averaging or '空'}，换算后再计算。"
        )
    if speed < 0:
        raise ValueError("风速不能为负。")
    speed_mph = to_mps(speed, speed_unit) / METERS_PER_SECOND_PER_MPH
    kz = velocity_pressure_coefficient(height_m * FEET_PER_METER, exposure)
    ke = ground_elevation_factor(elevation_m)
    q_psf = AIR_DENSITY * kz * topographic * directionality * ke * speed_mph**2
    return q_psf * KN_PER_M2_PER_PSF


def design_wind_pressure(
    velocity_pressure_kn_m2: float,
    net_coefficient: float,
    gust_factor: float = GUST_FACTOR,
) -> float:
    """设计风压 p = qh·G·CN，kN/m²。CN 朝向板面顶面为正。"""
    return velocity_pressure_kn_m2 * gust_factor * net_coefficient


def _slope_length_mm(geometry: dict[str, Any]) -> float:
    length = float(need(geometry, "module_length_mm", label="组件长度"))
    width = float(need(geometry, "module_width_mm", label="组件宽度"))
    rows = geometry.get("arrangement_rows")
    row_count = 1.0 if rows is None else float(rows)
    if row_count <= 0:
        raise ValueError("组件布置行数必须大于 0。")
    # 竖放时斜长取组件长度。朝向不改变面积，只在这里用于形心高度。
    along_slope = length if MODULE_ORIENTATION == "Portrait" else width
    return along_slope * row_count


def build(design_case: dict[str, Any], trace: list[dict[str, Any]]) -> list[dict[str, Any]]:
    site = design_case.get("site") or {}
    geometry = design_case.get("geometry") or {}
    speed = float(need(site, "wind_speed", label="风速"))
    unit = str(need(site, "wind_speed_unit", label="风速单位"))
    averaging = site.get("wind_speed_averaging")
    if averaging != THREE_SECOND:
        raise ValueError(
            f"式 26.10-1 使用 3 s 阵风。当前时距是 {averaging or '空'}，换算后再计算。"
        )
    elevation = site.get("altitude_m")
    elevation_m = float(elevation) if elevation is not None else None
    clearance = geometry.get("ground_clearance_mm")
    clearance_mm = 0.0 if clearance is None else float(clearance)
    slope_mm = _slope_length_mm(geometry)
    ke = ground_elevation_factor(elevation_m)
    trace_step(
        trace,
        "wind.ke",
        "ASCE 7-16 式 26.9-1",
        "Ke = exp(-0.0000362·zg)",
        f"zg = {0.0 if elevation_m is None else elevation_m * FEET_PER_METER:.1f} ft，Ke = {ke:.4f}",
        round(ke, 4),
        "1",
    )
    cases: list[dict[str, Any]] = []
    for tilt in WIND_TILTS_DEG:
        height_m = mean_panel_height_m(clearance_mm, slope_mm, tilt)
        qh = round(
            velocity_pressure(
                speed,
                unit,
                averaging,
                height_m,
                EXPOSURE_CATEGORY,
                elevation_m,
            ),
            4,
        )
        kz = velocity_pressure_coefficient(height_m * FEET_PER_METER, EXPOSURE_CATEGORY)
        speed_mph = to_mps(speed, unit) / METERS_PER_SECOND_PER_MPH
        trace_step(
            trace,
            FORMULA_Q,
            "ASCE 7-16 式 26.10-1；Exposure C；Kd = 0.85；Kzt = 1.0",
            "qh = 0.00256·Kz·Kzt·Kd·Ke·V²",
            (
                f"θ = {tilt:g}°，h = {height_m:.3f} m，Kz = {kz:.4f}，"
                f"V = {speed_mph:.2f} mph，qh = {qh}"
            ),
            qh,
            "kN/m2",
        )
        cases.append(
            load_case(
                f"W_QH_{int(tilt)}",
                f"速度风压 qh（倾角 {int(tilt)}°）",
                qh,
                "kN/m2",
                FORMULA_Q,
            )
        )
    return cases
