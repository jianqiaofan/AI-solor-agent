"""把原始资料解析成文本和表格，写到 pipeline.parse_documents 的 work_dir。"""

from extraction.parsers.collection_sheet import find_collection_sheet, read_collection_sheet

__all__ = ["find_collection_sheet", "read_collection_sheet"]
