"""面荷载按组件长度转成主梁线荷载。"""

from loads.tools.line_load import beam_line_cases, is_module_area_load, line_intensity, summary_lines


def test_line_intensity_uses_module_length() -> None:
    # 0.119 kN/m² × 2.384 m = 0.283696
    assert round(line_intensity(0.119, 2384), 4) == 0.2837
    try:
        line_intensity(0.1, 0)
    except ValueError as exc:
        assert "组件长度" in str(exc)
    else:
        raise AssertionError("组件长度为 0 时不应换算")


def test_velocity_pressure_is_not_a_module_area_load() -> None:
    assert is_module_area_load({"id": "D", "unit": "kN/m2", "value": 0.1})
    assert not is_module_area_load({"id": "W_QP_0", "unit": "kN/m2", "value": 0.5})
    assert not is_module_area_load({"id": "W_QH_60", "unit": "kN/m2", "value": 0.5})


def test_each_area_load_becomes_a_beam_line_load() -> None:
    cases, trace = beam_line_cases(
        [
            {"id": "D", "name": "组件自重", "value": 0.119, "unit": "kN/m2"},
            {"id": "W_QP_0", "name": "峰值速度风压", "value": 0.5, "unit": "kN/m2"},
            {"id": "W_0_F", "name": "板面风压", "value": -1.2, "unit": "kN/m2"},
        ],
        2384,
    )
    by_id = {item["id"]: item for item in cases}
    assert set(by_id) == {"D_LINE", "W_0_F_LINE"}
    assert by_id["D_LINE"]["value"] == 0.2837
    assert by_id["D_LINE"]["unit"] == "kN/m"
    assert by_id["D_LINE"]["target"] == "beam"
    assert by_id["W_0_F_LINE"]["value"] == round(-1.2 * 2.384, 4)
    assert trace[0]["expression"] == "w = p·L"
    assert "中线" in trace[0]["clause"]


def test_summary_keeps_only_the_extreme_wind_line_loads() -> None:
    lines = summary_lines(
        [
            {"id": "D", "name": "组件自重", "value": 0.1, "unit": "kN/m2"},
            {"id": "W_0_F", "name": "F", "value": 1.2, "unit": "kN/m2"},
            {"id": "W_0_H", "name": "H", "value": -0.7, "unit": "kN/m2"},
            {"id": "W_QP_0", "name": "qp", "value": 0.5, "unit": "kN/m2"},
        ],
        1000,
    )
    text = "\n".join(lines)
    assert "组件长度 1 m" in text
    assert "| 组件自重 | 0.1 kN/m |" in text
    assert "| 板面风压（0°，最大正风压） | 1.2 kN/m |" in text
    assert "| 板面风压（0°，最大负风压） | -0.7 kN/m |" in text
    assert "qp" not in text


if __name__ == "__main__":
    test_line_intensity_uses_module_length()
    test_velocity_pressure_is_not_a_module_area_load()
    test_each_area_load_becomes_a_beam_line_load()
    test_summary_keeps_only_the_extreme_wind_line_loads()
    print("ok")
