"""资料抽取子系统。命令行写出 draft；界面经人工确认后写出 confirmed。"""

from extraction.pipeline import extract_design_case, parse_documents

__all__ = ["extract_design_case", "parse_documents"]
