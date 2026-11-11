"""屋面雪荷载，ASCE 7-16 第 7 章。

资料中的雪荷载作为地面雪荷载 pg。跟踪支架只计算 0°：
60° 时雪自行滑下，不在组件上形成设计积雪。
"""

from typing import Any

from loads.basis import SNOW_TILTS_DEG
from loads.tools.records import load_case, need, trace_step
from loads.tools.units import KN_PER_M2_PER_PSF, to_kn_m2

FORMULA_FLAT = "snow.pf"
FORMULA_MIN = "snow.pm"
FORMULA_DESIGN = "snow.ps"

# 表 7.3-1，地形类别 C、完全暴露。开阔光伏场按完全暴露。
CE_FULLY_EXPOSED_C = 0.9
# 表 7.3-2，不采暖的开敞结构。
CT_UNHEATED_OPEN = 1.2
# 表 1.5-2，雪荷载重要性系数。
SNOW_IMPORTANCE = {"I": 0.8, "II": 1.0, "III": 1.1, "IV": 1.2}
LOW_SLOPE_DEG = 15.0
MINIMUM_PG_PSF = 20.0
RAIN_ON_SNOW_PSF = 5.0


def snow_pressure(
    ground_snow: float,
    unit: str,
    risk_category: str,
    tilt_deg: float = 0.0,
    exposure_factor: float = CE_FULLY_EXPOSED_C,
    thermal_factor: float = CT_UNHEATED_OPEN,
    module_width_mm: float | None = None,
) -> float:
    """0° 设计雪荷载，kN/m²。

    pf = 0.7·Ce·Ct·Is·pg（式 7.3-1）。坡度小于 15° 时不小于第 7.3.4 条的最低值。
    pg ≤ 20 psf 且坡度小于 W/50 时，另加第 7.10 条的 5 psf 雨夹雪。
    """
    if tilt_deg != 0:
        raise ValueError("雪荷载只计算 0°。60° 时雪自行滑下，不作为积雪工况。")
    if ground_snow < 0:
        raise ValueError("地面雪荷载不能为负。")
    importance = SNOW_IMPORTANCE.get(risk_category)
    if importance is None:
        raise ValueError(f"风险类别 {risk_category} 没有对应的雪荷载重要性系数。")

    pg = to_kn_m2(ground_snow, unit)
    flat = 0.7 * exposure_factor * thermal_factor * importance * pg
    pg_psf = pg / KN_PER_M2_PER_PSF
    if pg_psf <= MINIMUM_PG_PSF:
        minimum_psf = importance * pg_psf
    else:
        minimum_psf = importance * MINIMUM_PG_PSF
    minimum = minimum_psf * KN_PER_M2_PER_PSF
    pressure = max(flat, minimum)
    if pg_psf <= MINIMUM_PG_PSF and _rain_on_snow(tilt_deg, module_width_mm):
        pressure += RAIN_ON_SNOW_PSF * KN_PER_M2_PER_PSF
    return pressure


def _rain_on_snow(tilt_deg: float, module_width_mm: float | None) -> bool:
    """第 7.10 条：坡度（度）小于 W/50（W 为水平跨度，ft）时考虑雨夹雪。"""
    if module_width_mm is None or module_width_mm <= 0:
        return tilt_deg == 0
    width_ft = (module_width_mm / 1000.0) / 0.3048
    return tilt_deg < width_ft / 50.0


def build(design_case: dict[str, Any], trace: list[dict[str, Any]]) -> list[dict[str, Any]]:
    site = design_case.get("site") or {}
    geometry = design_case.get("geometry") or {}
    ground = float(need(site, "snow_load", label="雪荷载"))
    unit = str(need(site, "snow_load_unit", label="雪荷载单位"))
    category = str(need(site, "risk_category", label="风险类别"))
    width = geometry.get("module_width_mm")
    width_mm = float(width) if width is not None else None
    importance = SNOW_IMPORTANCE.get(category)
    if importance is None:
        raise ValueError(f"风险类别 {category} 没有对应的雪荷载重要性系数。")
    pg = to_kn_m2(ground, unit)
    cases: list[dict[str, Any]] = []
    for tilt in SNOW_TILTS_DEG:
        flat = round(0.7 * CE_FULLY_EXPOSED_C * CT_UNHEATED_OPEN * importance * pg, 4)
        trace_step(
            trace,
            FORMULA_FLAT,
            "ASCE 7-16 式 7.3-1",
            "pf = 0.7·Ce·Ct·Is·pg",
            (
                f"0.7×{CE_FULLY_EXPOSED_C}×{CT_UNHEATED_OPEN}×{importance}×{pg:.4f}"
                f" = {flat}"
            ),
            flat,
            "kN/m2",
        )
        pg_psf = pg / KN_PER_M2_PER_PSF
        if pg_psf <= MINIMUM_PG_PSF:
            minimum_psf = importance * pg_psf
            minimum_rule = "pg ≤ 20 psf，pm = Is×pg"
        else:
            minimum_psf = importance * MINIMUM_PG_PSF
            minimum_rule = "pg > 20 psf，pm = Is×20 psf"
        minimum = round(minimum_psf * KN_PER_M2_PER_PSF, 4)
        minimum_note = f"pg = {pg_psf:.2f} psf，{minimum_rule} = {minimum}"
        trace_step(
            trace,
            FORMULA_MIN,
            "ASCE 7-16 第 7.3.4 条",
            "pm = Is·pg（pg≤20 psf）或 Is·20 psf",
            minimum_note,
            minimum,
            "kN/m2",
        )
        pressure = round(
            snow_pressure(ground, unit, category, tilt, module_width_mm=width_mm),
            4,
        )
        balanced = round(max(flat, minimum), 4)
        if pressure != balanced:
            substitution = f"max({flat}, {minimum}) + 5 psf = {pressure}"
            expression = "ps = max(Cs·pf, pm) + 5 psf"
            clause = "ASCE 7-16 第 7.4 节与第 7.10 条"
        else:
            substitution = f"max({flat}, {minimum}) = {pressure}"
            expression = "ps = max(Cs·pf, pm)"
            clause = "ASCE 7-16 第 7.4 节，θ = 0° 时 Cs = 1.0；与 pm 取大值"
        trace_step(
            trace,
            FORMULA_DESIGN,
            clause,
            expression,
            substitution,
            pressure,
            "kN/m2",
        )
        cases.append(
            load_case(
                f"S_{int(tilt)}",
                f"雪荷载（倾角 {int(tilt)}°）",
                pressure,
                "kN/m2",
                FORMULA_DESIGN,
            )
        )
    return cases
