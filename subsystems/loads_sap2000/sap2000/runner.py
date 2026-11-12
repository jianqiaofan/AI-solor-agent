"""按线模和荷载文件驱动 SAP2000，并读回 analysis_result.json。

本机由 OAPI 打开 SAP2000 26。主梁线荷载直接加到主梁上。
窗口保持打开。应力比不在这一步验算。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sap2000.model import (
    analysis_document,
    beam_line_loads,
    combination_factors,
    members_from_line_model,
)
from sap2000.program import sap2000_executable


def run_analysis(
    design_case: dict[str, Any],
    loads: dict[str, Any],
    template_dir: Path,
    work_dir: Path,
    session: Any = None,
) -> dict[str, Any]:
    """返回符合 contracts/schemas/analysis_result.schema.json 的对象。

    work_dir 存放本次的模型文件。线模读取 work_dir 的上一级 line_model.json。
    """
    _ = template_dir
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
    members = members_from_line_model(line_model)
    cases = beam_line_loads(loads)
    combinations = combination_factors(loads, cases)
    model_path = Path(work_dir) / "model.sdb"
    active = session
    if active is None:
        from sap2000.api import SapSession

        active = SapSession(sap2000_executable())
    forces = active.run(members, cases, combinations, model_path)
    document = analysis_document(revision, str(model_path), members, forces)
    _validate(document)
    return document


def _validate(document: dict[str, Any]) -> None:
    schema_path = Path(__file__).resolve().parents[3] / "contracts" / "schemas" / "analysis_result.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    from jsonschema import Draft202012Validator

    Draft202012Validator(schema).validate(document)
