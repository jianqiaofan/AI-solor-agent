"""规范荷载工具：ASCE 7-16 与 EN 1991。"""

import math

from loads.tools import snow, wind
from loads.tools.code_loads import (
    _external_coefficient,
    moduleDead,
    snowASCE16,
    snowEN1991,
    tools_for_code,
    windASCE16,
    windEN1991,
)


def test_wind_asce16_matches_existing_builder() -> None:
    got = windASCE16(25.3, "m/s", "3 s gust", 2384, 1303, 800, altitude_m=217, arrangement_rows=1)
    trace: list[dict] = []
    expected = wind.build(
        {
            "site": {
                "wind_speed": 25.3,
                "wind_speed_unit": "m/s",
                "wind_speed_averaging": "3 s gust",
                "altitude_m": 217,
            },
            "geometry": {
                "module_length_mm": 2384,
                "module_width_mm": 1303,
                "ground_clearance_mm": 800,
                "arrangement_rows": 1,
            },
        },
        trace,
    )
    by_id = {item["id"]: item for item in got["cases"]}
    expected_by_id = {item["id"]: item for item in expected}
    assert {key: by_id[key] for key in expected_by_id} == expected_by_id
    assert got["trace"][: len(trace)] == trace
    assert got["code"] == "ASCE 7-16"
    qh = by_id["W_QH_0"]["value"]
    assert by_id["W_0_A_W"]["value"] == round(qh * 0.85 * 1.2, 4)
    assert by_id["W_0_B_L"]["value"] == round(qh * 0.85 * -0.1, 4)
    assert "W_60_A_W" not in by_id
    assert any("60°" in item for item in got["assumptions"])


def test_wind_asce16_rejects_ten_minute_mean() -> None:
    try:
        windASCE16(25.3, "m/s", "10 min mean", 2384, 1303, 800)
    except ValueError as exc:
        assert "3 s" in str(exc)
    else:
        raise AssertionError("10 min 平均风速不应进入 ASCE 7-16 工具")


def test_snow_asce16_matches_existing_builder() -> None:
    got = snowASCE16(1.5, "KN/m2", "I", module_width_mm=1303)
    trace: list[dict] = []
    expected = snow.build(
        {
            "site": {"snow_load": 1.5, "snow_load_unit": "KN/m2", "risk_category": "I"},
            "geometry": {"module_width_mm": 1303},
        },
        trace,
    )
    assert got["cases"] == expected
    assert got["trace"] == trace
    assert got["cases"][0]["value"] == 0.9072


def test_wind_en1991_peak_pressure_at_terrain_ii() -> None:
    # 0° 时形心高度等于离地 2 m，正好是地形 II 的 zmin。
    got = windEN1991(25, "m/s", "10 min mean", "II", 2000, 1000, 2000)
    z0 = 0.05
    kr = 0.19
    cr = kr * math.log(2.0 / z0)
    vm = cr * 25.0
    iv = 1.0 / math.log(2.0 / z0)
    qp = (1.0 + 7.0 * iv) * 0.5 * 1.25 * vm**2 / 1000.0
    by_id = {item["id"]: item["value"] for item in got["cases"]}
    assert by_id["W_QP_0"] == round(qp, 4)
    assert got["trace"][0]["formula_id"] == "wind.en.vb"
    assert by_id["W_QP_60"] > by_id["W_QP_0"]
    area = 2.0
    cpe_f = _external_coefficient(-1.8, -2.5, area)
    assert by_id["W_0_F"] == round(by_id["W_QP_0"] * cpe_f, 4)
    assert by_id["W_60_0_F"] == round(by_id["W_QP_60"] * 0.7, 4)
    assert by_id["W_60_180_F"] == round(
        by_id["W_QP_60"] * _external_coefficient(-0.5, -1.0, area),
        4,
    )
    assert by_id["W_60_90_H"] == round(
        by_id["W_QP_60"] * _external_coefficient(-1.0, -1.3, area),
        4,
    )


def test_wind_en1991_uses_zmin_when_panel_is_lower() -> None:
    at_two_metres = windEN1991(25, "m/s", "10 min mean", "II", 2000, 1000, 2000)
    below_zmin = windEN1991(25, "m/s", "10 min mean", "II", 2000, 1000, 500)
    at = {item["id"]: item["value"] for item in at_two_metres["cases"]}
    below = {item["id"]: item["value"] for item in below_zmin["cases"]}
    assert below["W_QP_0"] == at["W_QP_0"]


def test_wind_en1991_rejects_three_second_gust_and_bad_terrain() -> None:
    try:
        windEN1991(25, "m/s", "3 s gust", "II", 2000, 1000, 2000)
    except ValueError as exc:
        assert "10 min" in str(exc)
    else:
        raise AssertionError("3 s 阵风不应直接进入 EN 1991-1-4")
    try:
        windEN1991(25, "m/s", "10 min mean", "C", 2000, 1000, 2000)
    except ValueError as exc:
        assert "表 4.1" in str(exc)
    else:
        raise AssertionError("ASCE 的 Exposure C 不是欧标地形类别")


def test_snow_en1991_windswept_flat_roof() -> None:
    got = snowEN1991(1.5, "KN/m2", "windswept")
    # s = 0.8 × 0.8 × 1.0 × 1.5
    assert got["cases"][0]["value"] == 0.96
    sheltered = snowEN1991(1.5, "KN/m2", "sheltered")
    assert sheltered["cases"][0]["value"] == 1.44
    try:
        snowEN1991(1.5, "KN/m2", "C")
    except ValueError as exc:
        assert "windswept" in str(exc)
    else:
        raise AssertionError("不能用场地类型字母充当欧标暴露条件")


def test_module_dead_is_weight_over_area() -> None:
    got = moduleDead(37.7, 2384, 1303)
    assert got["action"] == "dead"
    assert got["cases"][0]["id"] == "D"
    assert got["cases"][0]["value"] == 0.1190
    assert got["cases"][0]["unit"] == "kN/m2"
    assert "m·g / (L·W)" in got["trace"][0]["expression"]


def test_tools_follow_the_design_code() -> None:
    asce = tools_for_code("USA(ASCE7-16)")
    europe = tools_for_code("Europe(Eurocode 1991-4)")
    assert [item.name for item in asce] == ["windASCE16", "snowASCE16", "moduleDead"]
    assert [item.name for item in europe] == ["windEN1991", "snowEN1991", "moduleDead"]
    try:
        tools_for_code("USA(ASCE7-10)")
    except ValueError as exc:
        assert "ASCE7-10" in str(exc)
    else:
        raise AssertionError("ASCE 7-10 不应调用 ASCE 7-16 工具")
    snow_tool = asce[1]
    got = snow_tool.invoke({"snow_load": 1.5, "snow_load_unit": "KN/m2", "risk_category": "I", "module_width_mm": 1303})
    assert got["cases"][0]["value"] == 0.9072


if __name__ == "__main__":
    test_wind_asce16_matches_existing_builder()
    test_wind_asce16_rejects_ten_minute_mean()
    test_snow_asce16_matches_existing_builder()
    test_wind_en1991_peak_pressure_at_terrain_ii()
    test_wind_en1991_uses_zmin_when_panel_is_lower()
    test_wind_en1991_rejects_three_second_gust_and_bad_terrain()
    test_snow_en1991_windswept_flat_roof()
    test_module_dead_is_weight_over_area()
    test_tools_follow_the_design_code()
    print("ok")
