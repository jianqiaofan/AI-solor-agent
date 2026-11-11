"""仓库路径。"""

from pathlib import Path


def repo_root() -> Path:
    """extraction 包位于 subsystems/extraction/extraction。"""
    return Path(__file__).resolve().parents[3]


def schema_path() -> Path:
    return repo_root() / "contracts" / "schemas" / "design_case.schema.json"


def design_case_path(project_id: str, revision: str) -> Path:
    return repo_root() / "projects" / project_id / revision / "design_case.json"
