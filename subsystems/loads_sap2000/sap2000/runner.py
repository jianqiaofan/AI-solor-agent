"""按线模和荷载文件驱动 SAP2000，挑选截面，并读回 analysis_result.json。

1. 全部杆件先用截面表里最轻的截面计算一次。各杆件刚度相同，内力只取决于几何和荷载。
2. 按这次的内力，为每根杆件挑选应力比不超过 0.95、单米重最轻的截面。
3. 用挑选的截面再算一次。应力比都不超过 1.0 就合格；否则按新的内力重新挑选，再算。

荷载文件没有组合时，按 ASCE 7-16 第 2.3.1 节强度设计组合补上。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sap2000.check import ACCEPT_LIMIT, PHI, SELECT_LIMIT, lightest_section, member_ratio
from sap2000.model import (
    analysis_document,
    beam_line_loads,
    combination_factors,
    members_from_line_model,
)
from sap2000.program import sap2000_executable
from sap2000.sections import load_sections

ROOT = Path(__file__).resolve().parents[3]
SECTION_TABLE = ROOT / "products" / "qizhuo30" / "sections" / "secton-octagon-165.json"
MAX_ROUNDS = 6


def run_analysis(
    design_case: dict[str, Any],
    loads: dict[str, Any],
    template_dir: Path,
    work_dir: Path,
    session: Any = None,
) -> dict[str, Any]:
    """返回符合 contracts/schemas/analysis_result.schema.json 的对象。"""
    _ = template_dir
    return run_design(design_case, loads, work_dir, session)[0]


def run_design(
    design_case: dict[str, Any],
    loads: dict[str, Any],
    work_dir: Path,
    session: Any = None,
    table_path: Path = SECTION_TABLE,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """返回 (analysis_result, 截面选择说明)。

    work_dir 存放本次的模型文件。线模读取 work_dir 的上一级 line_model.json。
    """
    revision = str(design_case.get("revision") or "").strip()
    if not revision:
        raise ValueError("设计案例没有修订号。")
    line_path = Path(work_dir).parent / "line_model.json"
    try:
        line_model = json.loads(line_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("线模文件读不出来。") from exc
    if not isinstance(line_model, dict):
        raise ValueError("线模文件读不出来。")
    table = load_sections(table_path)
    sections = {item["name"]: item for item in table["sections"]}
    fy = float(table["material"]["fy_mpa"])
    lightest = min(table["sections"], key=lambda item: float(item["mass_kg_per_m"]))

    members = members_from_line_model(line_model)
    cases = beam_line_loads(loads)
    combinations = combination_factors(_with_combinations(loads), cases)
    model_path = Path(work_dir) / "model.sdb"
    assignment = {member["id"]: lightest["name"] for member in members}
    for member in members:
        member["section"] = lightest["name"]

    active = session
    if active is None:
        from sap2000.api import SapSession

        active = SapSession(sap2000_executable())
    active.build(members, cases, combinations, table, model_path)

    rounds: list[dict[str, Any]] = []
    passed = False
    message = ""
    for number in range(1, MAX_ROUNDS + 1):
        forces = active.solve(assignment)
        solved = dict(assignment)
        checked = {
            member["id"]: member_ratio(forces[member["id"]], sections[assignment[member["id"]]], fy)
            for member in members
        }
        ratios = {key: value[0] for key, value in checked.items()}
        rounds.append({"round": number, "sections": dict(assignment), "ratios": _rounded(ratios)})
        chosen: dict[str, str] = {}
        missing: list[str] = []
        for member in members:
            picked = lightest_section(forces[member["id"]], table["sections"], fy, SELECT_LIMIT)
            if picked is None:
                missing.append(member["id"])
                picked = max(table["sections"], key=lambda item: float(item["mass_kg_per_m"]))
            chosen[member["id"]] = picked["name"]
        within = all(value <= ACCEPT_LIMIT for value in ratios.values())
        if within and (number > 1 or chosen == assignment):
            passed = True
            break
        if chosen == assignment:
            message = "截面表里最重的截面也不能让这些杆件的应力比降到 0.95 以下：" + "、".join(missing) + "。"
            break
        assignment = chosen
    else:
        message = f"算了 {MAX_ROUNDS} 次，应力比仍有超过 1.0 的杆件。"

    document = analysis_document(
        revision,
        str(model_path),
        members,
        forces,
        solved,
        ratios,
        passed,
    )
    _validate(document)
    design = _design(table_path, table, combinations, rounds, members, solved, checked, sections, message)
    return document, design


def _with_combinations(loads: dict[str, Any]) -> dict[str, Any]:
    if loads.get("combinations"):
        return loads
    from loads.tools.combinations import strength_combinations

    area_cases = [item for item in loads.get("cases") or [] if isinstance(item, dict)]
    return {**loads, "combinations": strength_combinations(area_cases)}


def _design(
    table_path: Path,
    table: dict[str, Any],
    combinations: list[dict[str, Any]],
    rounds: list[dict[str, Any]],
    members: list[dict[str, Any]],
    assignment: dict[str, str],
    checked: dict[str, tuple[float, str]],
    sections: dict[str, dict[str, Any]],
    message: str,
) -> dict[str, Any]:
    from loads.tools.combinations import formula

    rows = []
    total = 0.0
    for member in members:
        section = sections[assignment[member["id"]]]
        mass = float(section["mass_kg_per_m"]) * float(member["length"])
        total += mass
        ratio, governing = checked[member["id"]]
        rows.append(
            {
                "id": member["id"],
                "role": member["role"],
                "length_m": round(float(member["length"]), 4),
                "section": section["name"],
                "mass_kg_per_m": section["mass_kg_per_m"],
                "mass_kg": round(mass, 2),
                "ratio": round(ratio, 4),
                "governing": governing,
            }
        )
    return {
        "table": table_path.name,
        "material": table["material"]["name"],
        "fy_mpa": float(table["material"]["fy_mpa"]),
        "phi": PHI,
        "select_limit": SELECT_LIMIT,
        "accept_limit": ACCEPT_LIMIT,
        "combination_basis": "ASCE 7-16 第 2.3.1 节强度设计（LRFD）",
        "combinations": [
            {"id": item["id"], "formula": formula(item)} for item in combinations
        ],
        "check": (
            "每个输出点：σ = |N|/A + √(M2²+M3²)/W角轴，τ = √(V2²+V3²)/As + |T|/Wt，"
            "应力比 = √(σ²+3τ²)/(φ·fy)。只验算截面强度，立柱整体稳定和板件局部屈曲没有验算。"
        ),
        "rounds": rounds,
        "members": rows,
        "total_mass_kg": round(total, 2),
        "message": message,
    }


def _rounded(values: dict[str, float]) -> dict[str, float]:
    return {key: round(value, 4) for key, value in values.items()}


def _validate(document: dict[str, Any]) -> None:
    schema_path = ROOT / "contracts" / "schemas" / "analysis_result.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    from jsonschema import Draft202012Validator

    Draft202012Validator(schema).validate(document)
