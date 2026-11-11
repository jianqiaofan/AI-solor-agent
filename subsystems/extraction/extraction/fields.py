"""资料表字段与 design_case 属性的对照。

界面、解析和参数列表都读这一份，避免三处各写一遍。
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class FieldSpec:
    """一条资料表输入。

    key 是 design_case 里的点分路径。bands 用于单选：
    (控件横坐标, 印刷标签)。取值靠坐标，不靠导出值。
    unit_from 指向另一个字段，例如风速单位。
    """

    section: str
    key: str
    label: str
    kind: str
    pdf_field: str
    unit: str = ""
    choices: tuple[str, ...] = ()
    bands: tuple[tuple[float, str], ...] = ()
    unit_from: str = ""
    on_sheet: bool = True


# 第一项是该规范基本风速的时距，后面是客户资料里可能写成的其他时距。
# ASCE 7-05 另保留 fastest-mile：这一版基本风速已是 3 s 阵风，更早的资料仍会给 fastest-mile。
_THREE_SECOND = ("3 s gust", "10 min mean", "1 h mean")
WIND_AVERAGING_BY_CODE: dict[str, tuple[str, ...]] = {
    "USA(ASCE7-05)": ("3 s gust", "fastest-mile", "10 min mean", "1 h mean"),
    "USA(ASCE7-10)": _THREE_SECOND,
    "USA(ASCE7-16)": _THREE_SECOND,
    "Saudi(SBC301)": _THREE_SECOND,
    "India(IS875)": _THREE_SECOND,
    "Brazil(NBR 6123)": _THREE_SECOND,
    "Philippines(NSCP 2010)": _THREE_SECOND,
    "Mexico(CFE Code)": _THREE_SECOND,
    "Australia(AS 1170)": _THREE_SECOND,
    "Europe(Eurocode 1991-4)": ("10 min mean", "3 s gust", "1 h mean"),
}


def averaging_choices(design_code: str | None) -> tuple[str, ...]:
    """当前设计规范下，风速时距的可选项。未选规范时没有可选项。"""
    if not design_code:
        return ()
    return WIND_AVERAGING_BY_CODE.get(design_code, ())


SPECS: tuple[FieldSpec, ...] = (
    FieldSpec("基本信息", "site.client_name", "客户名称", "text", "CLIENT NAME"),
    FieldSpec("基本信息", "site.project_name", "项目名称", "text", "PROJECT NAME"),
    FieldSpec("基本信息", "site.country", "国家", "text", "country"),
    FieldSpec("基本信息", "site.capacity_mw_dc", "直流容量", "number", "capacity", "MW(DC)"),
    FieldSpec("场址", "site.latitude", "纬度", "text", "Latitude"),
    FieldSpec("场址", "site.latitude_hemisphere", "纬度半球", "enum", "N,S", choices=("N", "S")),
    FieldSpec("场址", "site.longitude", "经度", "text", "LONGTITUDE"),
    FieldSpec("场址", "site.longitude_hemisphere", "经度半球", "enum", "E-W", choices=("E", "W")),
    FieldSpec("场址", "site.altitude_m", "海拔", "number", "Altitude", "m"),
    FieldSpec(
        "场址",
        "site.geological_type",
        "场地类型",
        "radio",
        "Group14",
        choices=("Type 1", "Type 2", "Type 3", "Type 4"),
        bands=((70.2, "Type 1"), (201.5, "Type 2"), (354.1, "Type 3"), (495.5, "Type 4")),
    ),
    FieldSpec(
        "设计条件",
        "site.design_code",
        "设计规范",
        "enum",
        "design code",
        choices=(
            "USA(ASCE7-05)",
            "USA(ASCE7-10)",
            "USA(ASCE7-16)",
            "Saudi(SBC301)",
            "India(IS875)",
            "Brazil(NBR 6123)",
            "Philippines(NSCP 2010)",
            "Mexico(CFE Code)",
            "Australia(AS 1170)",
            "Europe(Eurocode 1991-4)",
        ),
    ),
    FieldSpec("设计条件", "site.wind_speed", "风速", "number", "WIND", unit_from="site.wind_speed_unit"),
    FieldSpec("设计条件", "site.wind_speed_unit", "风速单位", "enum", "wind uint", choices=("m/s", "km/h", "mph")),
    FieldSpec(
        "设计条件",
        "site.wind_speed_averaging",
        "风速时距",
        "enum",
        "",
        choices=("3 s gust", "fastest-mile", "10 min mean", "1 h mean"),
        on_sheet=False,
    ),
    FieldSpec("设计条件", "site.snow_load", "雪荷载", "number", "SNOW", unit_from="site.snow_load_unit"),
    FieldSpec("设计条件", "site.snow_load_unit", "雪荷载单位", "enum", "SNOW UNIT", choices=("KN/m2", "psf")),
    FieldSpec("设计条件", "site.seismic_load", "地震作用", "number", "seismic", unit_from="site.seismic_load_unit"),
    FieldSpec("设计条件", "site.seismic_load_unit", "地震单位", "enum", "Dropdown8", choices=("KN/m2", "psf")),
    FieldSpec("设计条件", "site.temperature_low_c", "最低气温", "number", "low temperature", "°C"),
    FieldSpec("设计条件", "site.temperature_high_c", "最高气温", "number", "high temperature", "°C"),
    FieldSpec("设计条件", "site.risk_category", "风险类别", "enum", "Dropdown1", choices=("I", "II", "III", "IV")),
    FieldSpec(
        "组件与支架",
        "geometry.mounting_type",
        "支架形式",
        "enum",
        "Mounting type",
        choices=("Single post", "Dual post", "Multi post", "Others"),
    ),
    FieldSpec("组件与支架", "geometry.module_length_mm", "组件长度", "number", "L", "mm"),
    FieldSpec("组件与支架", "geometry.module_width_mm", "组件宽度", "number", "Text1", "mm"),
    FieldSpec("组件与支架", "geometry.module_thickness_mm", "组件厚度", "number", "Text2", "mm"),
    FieldSpec("组件与支架", "geometry.module_weight_kg", "组件重量", "number", "Text4", "kg"),
    FieldSpec("组件与支架", "geometry.module_power_wp", "组件功率", "number", "Power", "Wp"),
    FieldSpec("组件与支架", "geometry.modules_per_string", "每串块数", "number", "Text8"),
    FieldSpec(
        "组件与支架",
        "geometry.module_type",
        "组件类型",
        "enum",
        "Dropdown2",
        choices=("Mono-facial", "Bifacial"),
    ),
    FieldSpec(
        "组件与支架",
        "geometry.module_orientation",
        "组件朝向",
        "radio",
        "Portrait",
        choices=("Portrait", "Landscape"),
        bands=((129.6, "Portrait"), (204.7, "Landscape")),
    ),
    FieldSpec("组件与支架", "geometry.arrangement_rows", "布置行数", "number", "string number"),
    FieldSpec("组件与支架", "geometry.arrangement_columns", "布置列数", "text", "Text6"),
    FieldSpec("组件与支架", "geometry.tilt_angle_deg", "倾角", "number", "tilt", "°"),
    FieldSpec(
        "基础",
        "geometry.foundation_type",
        "基础类型",
        "enum",
        "Foundation Type",
        choices=("Ramming Pile", "Concrete Pile", "Screw Pile", "PHC Pipe Pile"),
    ),
    FieldSpec("基础", "geometry.pile_embedment_depth_mm", "桩入土深度", "number", "Pile Depth in the soil", "mm"),
    FieldSpec("基础", "geometry.ground_clearance_mm", "组件离地高度", "number", "Text3", "mm"),
    FieldSpec(
        "材料",
        "materials.corrosion_category",
        "大气腐蚀等级",
        "radio",
        "Group16",
        choices=("C1", "C2", "C3", "C4", "C5"),
        bands=((88.2, "C1"), (176.0, "C2"), (261.8, "C3"), (348.4, "C4"), (433.8, "C5")),
    ),
    FieldSpec("附件", "site.documents.module_datasheet", "组件规格书", "bool", "Check Box1"),
    FieldSpec("附件", "site.documents.layout", "布置图", "bool", "Check Box2"),
    FieldSpec("附件", "site.documents.site_geological_plan", "场地地质平面", "bool", "Check Box3"),
    FieldSpec("附件", "site.documents.pull_out_test_report", "拉拔试验报告", "bool", "Check Box4"),
    FieldSpec("附件", "site.documents.topographic_drawing", "地形图", "bool", "Check Box5"),
    FieldSpec("附件", "site.documents.cable_route_plan", "电缆路由图", "bool", "Check Box6"),
    FieldSpec("备注", "site.remarks", "备注", "multiline", "Text5"),
)

SIGNATURE_FIELDS = frozenset({"CLIENT NAME", "design code", "Foundation Type", "WIND"})
