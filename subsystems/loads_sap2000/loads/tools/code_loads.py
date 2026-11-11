"""按规范分开的荷载工具。

模型按 design_code 调用不同函数，不要把一套公式套到另一本规范上。

- USA(ASCE7-16)：windASCE16、snowASCE16
- Europe(Eurocode 1991-4)：windEN1991、snowEN1991

美标风、雪的数值与 loads.tools.wind、loads.tools.snow 相同。
欧标风用 EN 1991-1-4 的峰值速度风压，欧标雪用 EN 1991-1-3 的屋面雪荷载。
两本规范目前都只算到风压本身，不乘面板体型系数或风力系数。
"""

from __future__ import annotations

import math
from typing import Any

from loads.basis import MODULE_ORIENTATION, WIND_TILTS_DEG
from loads.tools import snow, wind
from loads.tools.records import load_case, trace_step
from loads.tools.units import to_kn_m2, to_mps

# EN 1991-1-4 表 4.1。z0、zmin 的单位是 m。
_TERRAIN = {
    "0": (0.003, 1.0),
    "I": (0.01, 1.0),
    "II": (0.05, 2.0),
    "III": (0.3, 5.0),
    "IV": (1.0, 10.0),
}
_Z0_II = 0.05
_ZMAX_M = 200.0
# 式 4.8 的推荐空气密度，kg/m³。结果先得到 Pa，再换成 kN/m²。
_AIR_DENSITY = 1.25
# 推荐值。国家附录可能不同，这里不用国家附录。
_DIRECTION_FACTOR = 1.0
_SEASON_FACTOR = 1.0
_OROGRAPHY_FACTOR = 1.0
_TURBULENCE_FACTOR = 1.0

# EN 1991-1-3 表 5.1 的推荐暴露系数。
_SNOW_EXPOSURE = {"windswept": 0.8, "normal": 1.0, "sheltered": 1.2}
# 式 5.1。不采暖的开敞支架取推荐值 1.0。
_THERMAL_COEFFICIENT = 1.0
# 0° 平屋面，以及坡屋面在不超过 30° 时，μ1 都是 0.8。
_SHAPE_COEFFICIENT_FLAT = 0.8

_ASCE = "USA(ASCE7-16)"
_EN = "Europe(Eurocode 1991-4)"

# 图 27.3-4，通畅气流，θ = 0°。这一行上 γ = 0° 与 180° 的系数相同。
# 正号表示压力指向屋面顶面。W 是迎风半区，L 是背风半区。
_ASCE_CN_FLAT_CLEAR = (
    ("A", "W", 1.2),
    ("A", "L", 0.3),
    ("B", "W", -1.1),
    ("B", "L", -0.1),
)

# 表 7.2，锐檐、无女儿墙。I 区的正值和负值都要考虑。
_EN_FLAT_SHARP = (
    ("F", "F", -1.8, -2.5),
    ("G", "G", -1.2, -2.0),
    ("H", "H", -0.7, -1.2),
    ("I_POS", "I 正", 0.2, 0.2),
    ("I_NEG", "I 负", -0.2, -0.2),
)

# 表 7.3a，单坡屋面，α = 60°。风向 0° 与 180°。cpe,1 未单列时与 cpe,10 相同。
_EN_MONO_60 = (
    ("0", "F", 0.7, 0.7),
    ("0", "G", 0.7, 0.7),
    ("0", "H", 0.7, 0.7),
    ("180", "F", -0.5, -1.0),
    ("180", "G", -0.5, -0.5),
    ("180", "H", -0.5, -0.5),
)

# 表 7.3b，α = 60°，风向平行于屋檐。
_EN_MONO_60_PARALLEL = (
    ("Fup", -1.2, -2.0),
    ("Flow", -1.2, -2.0),
    ("G", -1.2, -2.0),
    ("H", -1.0, -1.3),
    ("I", -1.2, -1.2),
)


def windASCE16(
    wind_speed: float,
    wind_speed_unit: str,
    wind_speed_averaging: str,
    module_length_mm: float,
    module_width_mm: float,
    ground_clearance_mm: float,
    altitude_m: float | None = None,
    arrangement_rows: float | None = None,
) -> dict[str, Any]:
    """按 ASCE 7-16 计算跟踪支架的风荷载，单位 kN/m²。

    只在设计规范为 USA(ASCE7-16)、风速时距为 3 s gust 时调用。
    地面粗糙度固定为 Exposure C。0° 和 60° 都给出速度风压 qh。
    0° 再按图 27.3-4 通畅气流的净体型系数给出设计风压 p = qh·G·CN。
    60° 超出该图 θ ≤ 45° 的范围，不外推体型系数，没有设计风压。
    风速单位用 m/s、km/h 或 mph。没有海拔时不要传 altitude_m。
    """
    trace: list[dict[str, Any]] = []
    cases = wind.build(
        {
            "site": {
                "wind_speed": wind_speed,
                "wind_speed_unit": wind_speed_unit,
                "wind_speed_averaging": wind_speed_averaging,
                "altitude_m": altitude_m,
            },
            "geometry": {
                "module_length_mm": module_length_mm,
                "module_width_mm": module_width_mm,
                "ground_clearance_mm": ground_clearance_mm,
                "arrangement_rows": arrangement_rows,
            },
        },
        trace,
    )
    qh_flat = next(item["value"] for item in cases if item["id"] == "W_QH_0")
    cases.extend(_asce_flat_pressures(qh_flat, trace))
    return _pack(
        "ASCE 7-16",
        "wind",
        cases,
        trace,
        [
            "地面粗糙度为 Exposure C，不按场地类型换算。",
            "Kd = 0.85，Kzt = 1.0。没有海拔时 Ke = 1。阵风系数 G = 0.85。",
            "没有光伏板专条。0° 按开敞建筑的单坡自由屋面，取图 27.3-4 通畅气流。",
            "0° 时风向 γ = 0° 与 180° 的系数相同。正号指向板面顶面。回复只给出最大正风压和最大负风压。",
            "图 27.3-4 还要求 0.25 ≤ h/L ≤ 1.0。阵列顺风向长度还没有，这次没有核验 h/L。",
            "60° 超出图 27.3-4 的 θ ≤ 45°，规范没有允许从 45° 外推，所以 60° 只有速度风压 qh。",
        ],
    )


def snowASCE16(
    snow_load: float,
    snow_load_unit: str,
    risk_category: str,
    module_width_mm: float | None = None,
) -> dict[str, Any]:
    """按 ASCE 7-16 第 7 章计算 0° 屋面雪荷载，单位 kN/m²。

    只在设计规范为 USA(ASCE7-16) 时调用。
    snow_load 是地面雪荷载 pg，单位用 KN/m2 或 psf。
    risk_category 取 I、II、III 或 IV。60° 不计算：雪会自行滑下。
    """
    trace: list[dict[str, Any]] = []
    cases = snow.build(
        {
            "site": {
                "snow_load": snow_load,
                "snow_load_unit": snow_load_unit,
                "risk_category": risk_category,
            },
            "geometry": {"module_width_mm": module_width_mm},
        },
        trace,
    )
    return _pack(
        "ASCE 7-16",
        "snow",
        cases,
        trace,
        [
            "资料中的雪荷载作为地面雪荷载 pg。",
            "Ce = 0.9（地形 C、完全暴露），Ct = 1.2（不采暖开敞结构）。",
            "只计算 0°。60° 时雪自行滑下。",
        ],
    )


def windEN1991(
    wind_speed: float,
    wind_speed_unit: str,
    wind_speed_averaging: str,
    terrain_category: str,
    module_length_mm: float,
    module_width_mm: float,
    ground_clearance_mm: float,
    arrangement_rows: float | None = None,
) -> dict[str, Any]:
    """按 EN 1991-1-4 计算跟踪支架的风荷载，单位 kN/m²。

    只在设计规范为 Europe(Eurocode 1991-4)、风速时距为 10 min mean 时调用。
    terrain_category 取表 4.1 的 0、I、II、III 或 IV，不要用场地类型代替。
    先算 0° 和 60° 的峰值速度风压 qp。再用规范正文的推荐屋面外压系数：
    0° 用表 7.2 锐檐平屋面，60° 用表 7.3a 和表 7.3b 的单坡屋面。
    屋面风压 we = qp·cpe。不用国家附录，也不把雨篷表外推到 60°。
    """
    if wind_speed_averaging != "10 min mean":
        raise ValueError(
            "EN 1991-1-4 的基本风速是 10 min 平均。"
            f"当前时距是 {wind_speed_averaging or '空'}，不要在本工具里换算。"
        )
    speed = _real(wind_speed, "风速")
    if speed < 0:
        raise ValueError("风速不能为负。")
    length = _real(module_length_mm, "组件长度")
    width = _real(module_width_mm, "组件宽度")
    clearance = _real(ground_clearance_mm, "离地高度")
    if length <= 0 or width <= 0:
        raise ValueError("组件平面尺寸必须大于 0。")
    if clearance < 0:
        raise ValueError("离地高度不能为负。")
    z0, zmin, terrain = _terrain(terrain_category)
    vb0 = to_mps(speed, wind_speed_unit)
    vb = _DIRECTION_FACTOR * _SEASON_FACTOR * vb0
    slope_mm = _slope_length_mm(length, width, arrangement_rows)
    kr = 0.19 * (z0 / _Z0_II) ** 0.07

    trace: list[dict[str, Any]] = []
    trace_step(
        trace,
        "wind.en.vb",
        "EN 1991-1-4 式 4.1；推荐值 cdir = 1，cseason = 1",
        "vb = cdir·cseason·vb,0",
        f"vb,0 = {vb0:.3f} m/s，vb = {vb:.3f} m/s",
        round(vb, 4),
        "m/s",
    )
    cases: list[dict[str, Any]] = []
    for tilt in WIND_TILTS_DEG:
        height_m = wind.mean_panel_height_m(clearance, slope_mm, tilt)
        z_used = min(max(height_m, zmin), _ZMAX_M)
        cr = kr * math.log(z_used / z0)
        vm = cr * _OROGRAPHY_FACTOR * vb
        iv = _TURBULENCE_FACTOR / (_OROGRAPHY_FACTOR * math.log(z_used / z0))
        qp_pa = (1.0 + 7.0 * iv) * 0.5 * _AIR_DENSITY * vm**2
        qp = round(qp_pa / 1000.0, 4)
        trace_step(
            trace,
            "wind.en.qp",
            "EN 1991-1-4 式 4.4、4.7、4.8；ρ = 1.25 kg/m³；kI = 1；co = 1；z 低于 zmin 时按 zmin",
            "qp = [1 + 7·Iv]·0.5·ρ·vm²",
            (
                f"θ = {tilt:g}°，h = {height_m:.3f} m，z = {z_used:.3f} m，"
                f"地形 {terrain}，z0 = {z0:g} m，kr = {kr:.4f}，cr = {cr:.4f}，"
                f"vm = {vm:.3f} m/s，Iv = {iv:.4f}，qp = {qp}"
            ),
            qp,
            "kN/m2",
        )
        cases.append(
            load_case(
                f"W_QP_{int(tilt)}",
                f"峰值速度风压 qp（倾角 {int(tilt)}°）",
                qp,
                "kN/m2",
                "wind.en.qp",
            )
        )
    area = (length / 1000.0) * (width / 1000.0)
    qp_flat = next(item["value"] for item in cases if item["id"] == "W_QP_0")
    qp_steep = next(item["value"] for item in cases if item["id"] == "W_QP_60")
    for zone, label, cpe_10, cpe_1 in _EN_FLAT_SHARP:
        cases.append(
            _euro_surface(
                f"W_0_{zone}",
                f"板面风压（0°，平屋面 {label} 区）",
                qp_flat,
                cpe_10,
                cpe_1,
                area,
                "EN 1991-1-4 表 7.2，锐檐平屋面；式 5.1 we = qp·cpe；1 m² 与 10 m² 之间按面积插值",
                trace,
            )
        )
    for direction, zone, cpe_10, cpe_1 in _EN_MONO_60:
        cases.append(
            _euro_surface(
                f"W_60_{direction}_{zone}",
                f"板面风压（60°，风向 {direction}°，{zone} 区）",
                qp_steep,
                cpe_10,
                cpe_1,
                area,
                "EN 1991-1-4 表 7.3a，单坡屋面 α = 60°；式 5.1 we = qp·cpe",
                trace,
            )
        )
    for zone, cpe_10, cpe_1 in _EN_MONO_60_PARALLEL:
        cases.append(
            _euro_surface(
                f"W_60_90_{zone}",
                f"板面风压（60°，风向 90°，{zone} 区）",
                qp_steep,
                cpe_10,
                cpe_1,
                area,
                "EN 1991-1-4 表 7.3b，单坡屋面 α = 60°，风向平行于屋檐",
                trace,
            )
        )
    return _pack(
        "EN 1991-1-4",
        "wind",
        cases,
        trace,
        [
            "使用 EN 1991-1-4 正文推荐值，不是某一国的国家附录。",
            "cdir = 1，cseason = 1，co = 1，kI = 1，ρ = 1.25 kg/m³。不按海拔修正空气密度。",
            "参考高度取组件平面形心离地高度；低于该地形的 zmin 时，qp 按 zmin 计算。",
            "没有光伏板专条。0° 小于 5°，按平屋面表 7.2 的锐檐、无女儿墙。",
            "60° 用单坡建筑屋面表 7.3a（风向 0°、180°）和表 7.3b（风向 90°）。",
            "给出的是外表面风压 we = qp·cpe。雨篷净压表 7.6 只到 30°，60° 不外推。",
            "分区宽度取决于阵列宽度，这次还不能判断组件落在哪一区。回复里每个倾角只给出最大正风压和最大负风压。",
            "受风面积按单块组件。小于 1 m² 用 cpe,1，大于 10 m² 用 cpe,10，中间按对数插值。",
            f"本次地形类别为 {terrain}。",
        ],
    )


def snowEN1991(
    snow_load: float,
    snow_load_unit: str,
    exposure: str,
) -> dict[str, Any]:
    """按 EN 1991-1-3 计算 0° 屋面雪荷载，单位 kN/m²。

    欧标项目与 windEN1991 一起使用。雪荷载条文是 EN 1991-1-3，不是 EN 1991-1-4。
    snow_load 作为特征地面雪荷载 sk，单位用 KN/m2 或 psf。
    exposure 取 windswept、normal 或 sheltered，对应表 5.1 的 Ce = 0.8、1.0、1.2。
    四周无遮挡的光伏场用 windswept。不要把场地类型直接换成这个词。
    0° 时 μ1 = 0.8，Ct = 1.0。60° 不计算。
    """
    ground = _real(snow_load, "雪荷载")
    if ground < 0:
        raise ValueError("雪荷载不能为负。")
    exposure_name, ce = _snow_exposure(exposure)
    sk = to_kn_m2(ground, snow_load_unit)
    pressure = round(_SHAPE_COEFFICIENT_FLAT * ce * _THERMAL_COEFFICIENT * sk, 4)
    trace: list[dict[str, Any]] = []
    trace_step(
        trace,
        "snow.en.s",
        "EN 1991-1-3 式 5.1；0° 时 μ1 = 0.8；Ct = 1.0；不用国家附录",
        "s = μ1·Ce·Ct·sk",
        (
            f"μ1 = {_SHAPE_COEFFICIENT_FLAT}，Ce = {ce}（{exposure_name}），"
            f"Ct = {_THERMAL_COEFFICIENT}，sk = {sk:.4f}，s = {pressure}"
        ),
        pressure,
        "kN/m2",
    )
    cases = [
        load_case("S_0", "雪荷载（倾角 0°）", pressure, "kN/m2", "snow.en.s"),
    ]
    return _pack(
        "EN 1991-1-3",
        "snow",
        cases,
        trace,
        [
            "资料中的雪荷载作为特征地面雪荷载 sk。",
            "使用 EN 1991-1-3 推荐值，不是某一国的国家附录。",
            "只计算 0°。μ1 = 0.8，Ct = 1.0。",
            f"暴露系数按 {exposure_name} 取 Ce = {ce}。",
        ],
    )


def tools_for_code(design_code: str) -> list[Any]:
    """返回这一本规范供模型调用的工具。其他规范先不要拿这两套公式去算。"""
    functions = {
        _ASCE: (windASCE16, snowASCE16),
        _EN: (windEN1991, snowEN1991),
    }.get(design_code)
    if functions is None:
        raise ValueError(
            f"还没有 {design_code or '空'} 的荷载工具。"
            "目前只有 USA(ASCE7-16) 和 Europe(Eurocode 1991-4)。"
        )
    try:
        from langchain_core.tools import tool
    except ImportError as exc:
        raise RuntimeError("还没有安装 langchain-core，模型暂时不能调用这些工具。") from exc
    return [tool(fn) for fn in functions]


def _asce_flat_pressures(qh: float, trace: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for load_name, zone, coefficient in _ASCE_CN_FLAT_CLEAR:
        pressure = round(wind.design_wind_pressure(qh, coefficient), 4)
        half = "迎风半区" if zone == "W" else "背风半区"
        trace_step(
            trace,
            "wind.p",
            "ASCE 7-16 式 27.3-2；图 27.3-4，θ = 0°，通畅气流；G = 0.85",
            "p = qh·G·CN",
            f"工况 {load_name}，{half}，CN = {coefficient:g}，qh = {qh}，p = {pressure}",
            pressure,
            "kN/m2",
        )
        cases.append(
            load_case(
                f"W_0_{load_name}_{zone}",
                f"设计风压（0°，工况 {load_name}，{half}）",
                pressure,
                "kN/m2",
                "wind.p",
            )
        )
    return cases


def _euro_surface(
    case_id: str,
    name: str,
    qp: float,
    cpe_10: float,
    cpe_1: float,
    area_m2: float,
    clause: str,
    trace: list[dict[str, Any]],
) -> dict[str, Any]:
    coefficient = _external_coefficient(cpe_10, cpe_1, area_m2)
    pressure = round(qp * coefficient, 4)
    trace_step(
        trace,
        "wind.en.we",
        clause,
        "we = qp·cpe",
        (
            f"A = {area_m2:.3f} m²，cpe,10 = {cpe_10:g}，cpe,1 = {cpe_1:g}，"
            f"cpe = {coefficient:.4f}，qp = {qp}，we = {pressure}"
        ),
        pressure,
        "kN/m2",
    )
    return load_case(case_id, name, pressure, "kN/m2", "wind.en.we")


def _external_coefficient(cpe_10: float, cpe_1: float, area_m2: float) -> float:
    """第 7.2.1 条：1 m² 用 cpe,1，10 m² 用 cpe,10，中间按 log10(A) 插值。"""
    if area_m2 <= 1.0:
        return cpe_1
    if area_m2 >= 10.0:
        return cpe_10
    return cpe_1 - (cpe_1 - cpe_10) * math.log10(area_m2)


def _pack(
    code: str,
    action: str,
    cases: list[dict[str, Any]],
    trace: list[dict[str, Any]],
    assumptions: list[str],
) -> dict[str, Any]:
    return {
        "code": code,
        "action": action,
        "cases": cases,
        "trace": trace,
        "assumptions": assumptions,
    }


def _terrain(category: str) -> tuple[float, float, str]:
    key = str(category).strip().upper()
    try:
        z0, zmin = _TERRAIN[key]
    except KeyError as exc:
        raise ValueError("地形类别必须是 EN 1991-1-4 表 4.1 的 0、I、II、III 或 IV。") from exc
    return z0, zmin, key


def _snow_exposure(exposure: str) -> tuple[str, float]:
    key = str(exposure).strip().lower()
    try:
        return key, _SNOW_EXPOSURE[key]
    except KeyError as exc:
        raise ValueError("雪荷载暴露条件必须是 windswept、normal 或 sheltered。") from exc


def _slope_length_mm(length_mm: float, width_mm: float, rows: float | None) -> float:
    row_count = 1.0 if rows is None else float(rows)
    if row_count <= 0:
        raise ValueError("组件布置行数必须大于 0。")
    along_slope = length_mm if MODULE_ORIENTATION == "Portrait" else width_mm
    return along_slope * row_count


def _real(value: Any, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label}必须是数值。") from exc
    if not math.isfinite(number):
        raise ValueError(f"{label}必须是有限数值。")
    return number
