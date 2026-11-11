"""把客户资料目录串成未锁定的 design_case.json。

解析放在 parsers/，字段抽取放在 tools/。本文件只保留调用顺序。
人工在界面里确认；这里写出的 status 保持 draft。
"""

import json
from pathlib import Path
from typing import Any

from extraction.parsers.collection_sheet import find_collection_sheet, read_collection_sheet
from extraction.tools.design_case import build_design_case


def parse_documents(source_dir: Path, work_dir: Path) -> None:
    """在资料目录中找到 Collection Sheet，并把读数写到 work_dir。"""
    sheet = find_collection_sheet([source_dir])
    parsed = read_collection_sheet(sheet)
    work_dir.mkdir(parents=True, exist_ok=True)
    (work_dir / "collection_sheet.json").write_text(
        json.dumps(parsed, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def extract_design_case(work_dir: Path) -> dict[str, Any]:
    """返回符合 contracts/schemas/design_case.schema.json 的草稿。

    site、geometry、materials 带上 schema 中的全部键，空白为 null。
    """
    parsed = json.loads((work_dir / "collection_sheet.json").read_text(encoding="utf-8"))
    return build_design_case(parsed, status="draft")
