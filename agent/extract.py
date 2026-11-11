"""从当前项目的资料目录提取设计参数，写出成果里的 design_case.json。"""

from __future__ import annotations

import sys
from pathlib import Path

from agent.settings import ROOT
from agent.store import MATERIALS_DIR, RESULTS_DIR, Store

class ExtractionError(Exception):
    pass


def extract_project_materials(store: Store, project_id: str) -> tuple[str, bool]:
    project = next((item for item in store.list_projects() if item["id"] == project_id), None)
    if project is None:
        raise ExtractionError("没有这个项目。")
    materials = store.projects_root / project["name"] / MATERIALS_DIR
    output = store.projects_root / project["name"] / RESULTS_DIR / "design_case.json"
    case = _run(materials, output, project["name"])
    relative = f"projects/{project['name']}/成果/design_case.json"
    return _describe(case, relative), True


def _run(materials: Path, output: Path, project_name: str) -> dict:
    _ensure_extraction_path()
    from extraction.parsers.collection_sheet import AmbiguousCollectionSheet, CollectionSheetNotFound
    from extraction.pipeline import extract_design_case, parse_documents
    from extraction.tools.design_case import write_design_case

    if not materials.is_dir():
        raise ExtractionError("还没有资料目录。请先把资料放进这个项目的「资料」。")
    work_dir = output.parent / "parsed"
    try:
        parse_documents(materials, work_dir)
        case = extract_design_case(work_dir)
    except CollectionSheetNotFound as exc:
        raise ExtractionError(str(exc)) from exc
    except AmbiguousCollectionSheet as exc:
        raise ExtractionError(str(exc)) from exc
    except OSError as exc:
        raise ExtractionError("资料没有读出来。") from exc
    case["project_id"] = project_name
    try:
        write_design_case(case, output)
    except ValueError as exc:
        raise ExtractionError(str(exc)) from exc
    except OSError as exc:
        raise ExtractionError("design_case.json 没有写进成果。") from exc
    return case


def _describe(case: dict, relative: str) -> str:
    filled: list[str] = []
    for item in case.get("parameters") or []:
        value = item.get("value")
        if value is None or value == "":
            continue
        unit = str(item.get("unit") or "").strip()
        shown = f"{value} {unit}".strip()
        filled.append(f"{item.get('name')}：{shown}")
    lines = [
        f"已从资料里提取设计参数，草稿写在 {relative}。",
        "文件结构和 fixtures/design_case.sample.json 一样，状态是 draft。",
    ]
    if not filled:
        lines.append("资料表上这些项都还是空的，需要再核对。")
        return "\n".join(lines)
    lines.append("有值的参数：")
    lines.extend(f"- {line}" for line in filled[:12])
    if len(filled) > 12:
        lines.append(f"其余 {len(filled) - 12} 项也在这个文件里。")
    lines.append("空着的项仍是 null。确认之前，不会拿这份草稿去算荷载。")
    return "\n".join(lines)


def _ensure_extraction_path() -> None:
    package_root = str(ROOT / "subsystems" / "extraction")
    if package_root not in sys.path:
        sys.path.insert(0, package_root)
