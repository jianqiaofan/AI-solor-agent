"""把资料表读数装配成 design_case。"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from extraction.fields import SPECS, FieldSpec
from extraction.paths import schema_path


def assign(target: dict[str, Any], dotted: str, value: Any) -> None:
    parts = dotted.split(".")
    cursor = target
    for part in parts[:-1]:
        child = cursor.get(part)
        if not isinstance(child, dict):
            child = {}
            cursor[part] = child
        cursor = child
    cursor[parts[-1]] = value


def lookup(target: dict[str, Any], dotted: str) -> Any:
    cursor: Any = target
    for part in dotted.split("."):
        if not isinstance(cursor, dict) or part not in cursor:
            return None
        cursor = cursor[part]
    return cursor


def blank_case(
    project_id: str = "PROJECT",
    revision: str = "r0",
    status: str = "draft",
    product_family: str = "fixed_tilt",
) -> dict[str, Any]:
    """带全部键的空案例。没填的值是 None。"""
    case: dict[str, Any] = {
        "schema_version": "1.0.0",
        "project_id": project_id,
        "revision": revision,
        "product_family": product_family,
        "status": status,
        "site": {},
        "geometry": {},
        "materials": {},
        "code_pack": None,
        "parameters": [],
    }
    for spec in SPECS:
        assign(case, spec.key, None)
    return case


def project_id_from_name(project_name: str | None) -> str:
    """用项目名称生成目录名。用户仍可在窗体里改。"""
    if not project_name:
        return "PROJECT"
    normalized = unicodedata.normalize("NFKD", project_name)
    ascii_name = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^A-Za-z0-9]+", "", ascii_name)
    return slug or "PROJECT"


def _unit(spec: FieldSpec, case: dict[str, Any]) -> str:
    if spec.unit_from:
        unit = lookup(case, spec.unit_from)
        return unit if isinstance(unit, str) else ""
    return spec.unit


def build_parameters(
    case: dict[str, Any],
    extracted: dict[str, Any],
    source_name: str,
) -> list[dict[str, Any]]:
    """非空字段写入 parameters。与抽取值相同的标 extracted，改过的标 confirmed。"""
    parameters: list[dict[str, Any]] = []
    for spec in SPECS:
        value = lookup(case, spec.key)
        if value is None:
            continue
        original = extracted.get(spec.key)
        if not spec.on_sheet or value != original:
            status = "confirmed"
            source = "用户在确认窗体中填写"
        else:
            status = "extracted"
            source = f"{source_name}#field:{spec.pdf_field}"
        parameters.append(
            {
                "name": spec.key,
                "value": value,
                "unit": _unit(spec, case),
                "status": status,
                "source": source,
            }
        )
    return parameters


def build_design_case(
    parsed: dict[str, Any],
    *,
    project_id: str | None = None,
    revision: str = "r0",
    status: str = "draft",
    product_family: str = "fixed_tilt",
) -> dict[str, Any]:
    values = parsed.get("values", {})
    name = values.get("site.project_name")
    case = blank_case(
        project_id or project_id_from_name(name if isinstance(name, str) else None),
        revision,
        status,
        product_family,
    )
    for spec in SPECS:
        assign(case, spec.key, values.get(spec.key))
    case["code_pack"] = case["site"]["design_code"]
    case["parameters"] = build_parameters(case, values, parsed.get("source_name", "collection_sheet.pdf"))
    return case


def validate_design_case(case: dict[str, Any]) -> None:
    schema = json.loads(schema_path().read_text(encoding="utf-8"))
    try:
        Draft202012Validator(schema).validate(case)
    except ValidationError as exc:
        location = ".".join(str(part) for part in exc.absolute_path) or "design_case"
        raise ValueError(f"{location}：{exc.message}") from exc


def write_design_case(case: dict[str, Any], output: Path, parsed: dict[str, Any] | None = None) -> None:
    validate_design_case(case)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(case, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if parsed is None:
        return
    work_dir = output.parent / "parsed"
    work_dir.mkdir(parents=True, exist_ok=True)
    (work_dir / "collection_sheet.json").write_text(
        json.dumps(parsed, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
