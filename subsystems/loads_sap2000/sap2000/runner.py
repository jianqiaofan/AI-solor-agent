"""按模板和荷载文件驱动 SAP2000，并读回 analysis_result.json。

建模步骤以你提供的 skill 为准，放到 sap2000/skill/SKILL.md。
模板模型放到 sap2000/templates/。
"""

from pathlib import Path
from typing import Any


def run_analysis(
    design_case: dict[str, Any],
    loads: dict[str, Any],
    template_dir: Path,
    work_dir: Path,
) -> dict[str, Any]:
    """返回符合 contracts/schemas/analysis_result.schema.json 的对象。

    work_dir 用于存放本次的模型文件，并写入结果里的 model_file。
    """
    if design_case.get("status") != "confirmed":
        raise ValueError("SAP2000 只接受 status 为 confirmed 的 design_case。")
    _ = (loads, template_dir, work_dir)
    raise NotImplementedError("请按 sap2000/skill/SKILL.md 实现建模、运行和结果读回。")
