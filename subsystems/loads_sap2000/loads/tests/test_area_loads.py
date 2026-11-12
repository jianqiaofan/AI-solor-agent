"""组件面荷载：自重、速度风压、屋面雪荷载。"""

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from loads.pipeline import build_loads
from loads.tools.dead import dead_pressure
from loads.tools.snow import snow_pressure
from loads.tools.wind import (
    design_wind_pressure,
    velocity_pressure,
    velocity_pressure_coefficient,
)


def test_dead_pressure() -> None:
    pressure = dead_pressure(37.7, 2384, 1303)
    area = 2.384 * 1.303
    expected = 37.7 * 9.80665 / 1000.0 / area
    assert abs(pressure - expected) < 1e-9
    assert round(pressure, 4) == 0.1190


def test_kz_matches_exposure_c_table() -> None:
    assert abs(velocity_pressure_coefficient(10, "C") - 0.85) < 0.01
    assert abs(velocity_pressure_coefficient(40, "C") - 1.04) < 0.015
    assert abs(velocity_pressure_coefficient(100, "C") - 1.26) < 0.015


def test_velocity_pressure_uses_three_second_gust() -> None:
    qh = velocity_pressure(25.3, "m/s", "3 s gust", height_m=1.0, elevation_m=217)
    assert qh > 0
    try:
        velocity_pressure(25.3, "m/s", "10 min mean", height_m=1.0)
    except ValueError as exc:
        assert "3 s" in str(exc)
    else:
        raise AssertionError("10 min 平均风速不应直接进入式 26.10-1")


def test_design_wind_pressure() -> None:
    assert design_wind_pressure(1.0, -1.2) == -1.02


def test_snow_at_zero_for_risk_category_i() -> None:
    pressure = snow_pressure(1.5, "KN/m2", "I", 0, module_width_mm=1303)
    # pf = 0.7*0.9*1.2*0.8*1.5 = 0.9072，高于 pm
    assert round(pressure, 4) == 0.9072
    try:
        snow_pressure(1.5, "KN/m2", "I", 60)
    except ValueError as exc:
        assert "0°" in str(exc)
    else:
        raise AssertionError("60° 不应作为雪荷载工况")


def test_build_loads_matches_schema() -> None:
    case = {
        "schema_version": "1.0.0",
        "project_id": "SAMPLE",
        "revision": "r0",
        "product_family": "tracker",
        "status": "confirmed",
        "site": {
            "wind_speed": 25.3,
            "wind_speed_unit": "m/s",
            "wind_speed_averaging": "3 s gust",
            "snow_load": 1.5,
            "snow_load_unit": "KN/m2",
            "risk_category": "I",
            "altitude_m": 217,
        },
        "geometry": {
            "module_length_mm": 2384,
            "module_width_mm": 1303,
            "module_weight_kg": 37.7,
            "arrangement_rows": 1,
            "ground_clearance_mm": 800,
        },
    }
    loads = build_loads(case)
    schema_path = Path(__file__).resolve().parents[4] / "contracts" / "schemas" / "loads.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(loads)
    by_id = {item["id"]: item["value"] for item in loads["cases"]}
    assert by_id["D"] == 0.1190
    assert by_id["S_0"] == 0.9072
    assert by_id["W_QH_0"] == by_id["W_QH_60"]
    assert by_id["W_QH_0"] > 0
    assert [item["id"] for item in loads["combinations"]] == ["LRFD1", "LRFD2_S_0", "LRFD3_S_0"]


if __name__ == "__main__":
    test_dead_pressure()
    test_kz_matches_exposure_c_table()
    test_velocity_pressure_uses_three_second_gust()
    test_design_wind_pressure()
    test_snow_at_zero_for_risk_category_i()
    test_build_loads_matches_schema()
    print("ok")
