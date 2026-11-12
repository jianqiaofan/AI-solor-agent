"""把线模和线荷载整理成 SAP2000 要算的杆件，并取出最大内力。

项目还没有截面。主梁和立柱使用同一个刚度，柱脚铰接，柱顶刚接。
线弹性静力的内力只取决于这个相对刚度，不代表已经选定的产品截面。
"""

from __future__ import annotations

from typing import Any

SECTION = "等刚度"
FORCE_KEYS = ("N", "Vy", "Vz", "T", "My", "Mz")
_SAP_KEYS = ("P", "V2", "V3", "T", "M2", "M3")


def members_from_line_model(line_model: dict[str, Any]) -> list[dict[str, Any]]:
    if line_model.get("units") != "mm":
        raise ValueError("线模单位不是 mm。")
    if line_model.get("issues"):
        raise ValueError("线模还有未解决的问题，不能计算。")
    beam = line_model.get("beam")
    if not isinstance(beam, dict):
        raise ValueError("线模没有主梁。")
    start = _point_mm(beam.get("start"), "主梁起点")
    end = _point_mm(beam.get("end"), "主梁终点")
    columns = line_model.get("columns")
    if not isinstance(columns, list) or not columns:
        raise ValueError("线模没有立柱，不能计算。")
    ordered = sorted(columns, key=lambda item: float(item["y_mm"]))
    stations = [start[1], *[float(item["y_mm"]) for item in ordered], end[1]]
    members: list[dict[str, Any]] = []
    beam_count = 0
    for left, right in zip(stations, stations[1:]):
        if abs(right - left) <= 0.05:
            continue
        beam_count += 1
        members.append(
            _member(
                f"B{beam_count}",
                "beam",
                (start[0], left, start[2]),
                (end[0], right, end[2]),
            )
        )
    for index, column in enumerate(ordered, start=1):
        bottom = _point_mm(column.get("bottom"), f"立柱 {index} 下端")
        top = _point_mm(column.get("top"), f"立柱 {index} 上端")
        members.append(_member(f"C{index}", "column", bottom, top, base=bottom))
    return members


def beam_line_loads(loads: dict[str, Any]) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for item in loads.get("cases") or []:
        if not isinstance(item, dict):
            continue
        if item.get("target") != "beam" or item.get("unit") != "kN/m":
            continue
        found.append(
            {
                "id": str(item["id"]),
                "name": str(item.get("name") or item["id"]),
                "value": float(item["value"]),
                "pattern": _pattern_type(str(item["id"])),
            }
        )
    if not found:
        raise ValueError("荷载文件里没有主梁线荷载。")
    return found


def combination_factors(
    loads: dict[str, Any],
    cases: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """组合里的面荷载编号改成对应的线荷载。没有组合就返回空表。"""
    by_id = {item["id"] for item in cases}
    combos: list[dict[str, Any]] = []
    for combo in loads.get("combinations") or []:
        if not isinstance(combo, dict):
            continue
        factors: list[dict[str, Any]] = []
        for item in combo.get("factors") or []:
            case_id = str(item["case_id"])
            line_id = case_id if case_id in by_id else f"{case_id}_LINE"
            if line_id not in by_id:
                raise ValueError(f"组合 {combo.get('id')} 用了没有线荷载的工况 {case_id}。")
            factors.append({"case_id": line_id, "factor": float(item["factor"])})
        combos.append({"id": str(combo["id"]), "factors": factors})
    return combos


def extreme_forces(rows: list[dict[str, float]]) -> dict[str, float]:
    """每个分量保留绝对值最大的那个，正负号不动。"""
    if not rows:
        raise ValueError("SAP2000 没有返回杆件内力。")
    forces: dict[str, float] = {}
    for key, sap_key in zip(FORCE_KEYS, _SAP_KEYS):
        chosen = max(rows, key=lambda row: abs(float(row[sap_key])))
        forces[key] = round(float(chosen[sap_key]), 4)
    return forces


def analysis_document(
    revision: str,
    model_file: str,
    members: list[dict[str, Any]],
    forces_by_member: dict[str, list[dict[str, float]]],
) -> dict[str, Any]:
    recorded = []
    for member in members:
        recorded.append(
            {
                "id": member["id"],
                "section": SECTION,
                "length": round(float(member["length"]), 4),
                "forces": extreme_forces(forces_by_member[member["id"]]),
                "ratio": -1,
            }
        )
    return {
        "schema_version": "1.0.0",
        "design_case_revision": revision,
        "model_file": model_file,
        "template": "line-model",
        "check_status": "not_checked",
        "members": recorded,
        "reactions": [],
        "displacements": [],
    }


def report(result: dict[str, Any], program: str) -> str:
    lines = [
        f"已用 SAP2000 完成计算：{program}。",
        "项目没有给出截面。主梁和立柱用同一个刚度，柱脚铰接，柱顶刚接。内力是这个模型的结果。",
        "每个内力分量取全部已算工况里绝对值最大的值，并保留正负号。正值指向下方。",
        "应力比还没有验算。",
        f"模型文件：{result['model_file']}。",
    ]
    for member in result["members"]:
        force = member["forces"]
        lines.append(
            f"{member['id']}  L={member['length']} m  "
            f"N={force['N']} kN  Vy={force['Vy']} kN  Vz={force['Vz']} kN  "
            f"T={force['T']} kN·m  My={force['My']} kN·m  Mz={force['Mz']} kN·m"
        )
    return "\n".join(lines)


def _member(
    name: str,
    role: str,
    i_mm: tuple[float, float, float],
    j_mm: tuple[float, float, float],
    base: tuple[float, float, float] | None = None,
) -> dict[str, Any]:
    i_m = tuple(value / 1000.0 for value in i_mm)
    j_m = tuple(value / 1000.0 for value in j_mm)
    length = sum((b - a) ** 2 for a, b in zip(i_m, j_m)) ** 0.5
    member: dict[str, Any] = {
        "id": name,
        "role": role,
        "section": SECTION,
        "i": i_m,
        "j": j_m,
        "length": length,
    }
    if base is not None:
        member["base"] = tuple(value / 1000.0 for value in base)
    return member


def _point_mm(value: Any, label: str) -> tuple[float, float, float]:
    if not isinstance(value, list) or len(value) != 3:
        raise ValueError(f"线模的{label}不是三维坐标。")
    return float(value[0]), float(value[1]), float(value[2])


def _pattern_type(case_id: str) -> int:
    stem = case_id.removesuffix("_LINE")
    if stem == "D" or stem.startswith("D_"):
        return 1
    if stem.startswith("S_") or stem == "S":
        return 7
    if stem.startswith("W_"):
        return 6
    return 8
