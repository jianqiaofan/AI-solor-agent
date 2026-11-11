"""核对空案例和一份真实资料表都能通过 schema。"""

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from extraction.fields import WIND_AVERAGING_BY_CODE
from extraction.parsers.collection_sheet import read_collection_sheet
from extraction.paths import schema_path
from extraction.tools.design_case import blank_case, build_design_case


def _validator() -> Draft202012Validator:
    schema = json.loads(schema_path().read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


def test_blank_case() -> None:
    case = blank_case()
    _validator().validate(case)
    assert case["site"]["wind_speed_averaging"] is None


def test_averaging_follows_design_code() -> None:
    schema = json.loads(schema_path().read_text(encoding="utf-8"))
    design_codes = [
        code
        for code in schema["$defs"]["site"]["properties"]["design_code"]["enum"]
        if code is not None
    ]
    assert set(WIND_AVERAGING_BY_CODE) == set(design_codes)
    validator = _validator()
    for code, choices in WIND_AVERAGING_BY_CODE.items():
        case = blank_case()
        case["site"]["design_code"] = code
        case["code_pack"] = code
        case["site"]["wind_speed_averaging"] = choices[0]
        validator.validate(case)
    rejected = blank_case()
    rejected["site"]["design_code"] = "USA(ASCE7-16)"
    rejected["site"]["wind_speed_averaging"] = "fastest-mile"
    try:
        validator.validate(rejected)
    except ValidationError:
        return
    raise AssertionError("ASCE 7-16 不应接受 fastest-mile")


def test_saved_cases_have_averaging() -> None:
    validator = _validator()
    root = schema_path().parents[2]
    for relative in (
        "fixtures/design_case.sample.json",
        "projects/Barabantt/r0/design_case.json",
    ):
        case = json.loads((root / relative).read_text(encoding="utf-8"))
        validator.validate(case)
        assert "wind_speed_averaging" in case["site"]


def test_sheet(pdf: Path) -> None:
    case = build_design_case(read_collection_sheet(pdf), revision="r0", status="draft")
    _validator().validate(case)
    site = case["site"]
    geometry = case["geometry"]
    assert site["client_name"] == "SM"
    assert site["country"] == "Romania"
    assert site["capacity_mw_dc"] == 32.209
    assert site["latitude_hemisphere"] == "N"
    assert site["longitude_hemisphere"] == "E"
    assert site["altitude_m"] == 217
    assert site["design_code"] == "Europe(Eurocode 1991-4)"
    assert case["code_pack"] == "Europe(Eurocode 1991-4)"
    assert site["wind_speed"] == 25.3
    assert site["wind_speed_unit"] == "m/s"
    assert site["snow_load"] == 1.5
    assert site["seismic_load"] == 0.78
    assert site["temperature_low_c"] is None
    assert site["geological_type"] == "Type 2"
    assert site["documents"]["module_datasheet"] is False
    assert geometry["mounting_type"] == "Dual post"
    assert geometry["module_length_mm"] == 2384
    assert geometry["module_width_mm"] == 1303
    assert geometry["module_thickness_mm"] == 33
    assert geometry["module_orientation"] is None
    assert geometry["arrangement_rows"] == 2
    assert geometry["arrangement_columns"] == "11/22"
    assert geometry["foundation_type"] == "Ramming Pile"
    assert geometry["pile_embedment_depth_mm"] is None
    assert geometry["ground_clearance_mm"] == 800
    assert case["materials"]["corrosion_category"] == "C3"
    assert case["status"] == "draft"
    assert any(item["name"] == "site.wind_speed" and item["status"] == "extracted" for item in case["parameters"])


if __name__ == "__main__":
    test_blank_case()
    test_averaging_follows_design_code()
    test_saved_cases_have_averaging()
    if len(sys.argv) > 1:
        test_sheet(Path(sys.argv[1]))
    print("ok")
