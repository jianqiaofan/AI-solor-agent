"""从固定倾角资料表 PDF 读取表单域。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pymupdf

from extraction.fields import SPECS, SIGNATURE_FIELDS, FieldSpec

_CHECK_ON = {"yes", "on", "1", "true", "是"}
_CHECK_OFF = {"off", "0", "no", "false", "否", ""}
_RADIO_OFF = {"", "off"}


class CollectionSheetNotFound(FileNotFoundError):
    """选择的资料里没有这份采集表。"""


class AmbiguousCollectionSheet(RuntimeError):
    """选择的资料里有多份采集表。"""


def iter_files(paths: list[Path]) -> list[Path]:
    """文件直接收录；目录则递归展开。"""
    found: list[Path] = []
    for path in paths:
        if path.is_dir():
            found.extend(item for item in path.rglob("*") if item.is_file())
        elif path.is_file():
            found.append(path)
    return found


def _name_matches(path: Path) -> bool:
    stem = path.stem.lower().replace("-", "_").replace(" ", "_")
    return "collection_sheet" in stem or "data_collection" in stem


def _form_field_names(path: Path) -> set[str]:
    try:
        document = pymupdf.open(path)
    except Exception:
        return set()
    try:
        if document.page_count < 1 or not document.is_form_pdf:
            return set()
        return {widget.field_name for widget in (document[0].widgets() or [])}
    finally:
        document.close()


def find_collection_sheet(paths: list[Path]) -> Path:
    """在用户选择的文件中定位 Design Data Collection Sheet。"""
    pdfs = [path for path in iter_files(paths) if path.suffix.lower() == ".pdf"]
    named = [path for path in pdfs if _name_matches(path)]
    if len(named) > 1:
        names = "、".join(path.name for path in named)
        raise AmbiguousCollectionSheet(f"找到多份资料表：{names}。请只保留一份。")
    if len(named) == 1:
        return named[0]

    matched = [path for path in pdfs if SIGNATURE_FIELDS <= _form_field_names(path)]
    if len(matched) > 1:
        names = "、".join(path.name for path in matched)
        raise AmbiguousCollectionSheet(f"找到多份资料表：{names}。请只保留一份。")
    if len(matched) == 1:
        return matched[0]
    raise CollectionSheetNotFound(
        "没有找到 Design Data Collection Sheet。请放入文件名包含 Collection_Sheet 的 PDF。"
    )


def _text(widgets: list[Any]) -> str | None:
    if not widgets:
        return None
    raw = widgets[0].field_value
    if raw is None:
        return None
    text = str(raw).strip()
    return text or None


def _number(widgets: list[Any]) -> float | int | None:
    text = _text(widgets)
    if text is None:
        return None
    try:
        number = float(text.replace(",", ""))
    except ValueError:
        return None
    if number.is_integer():
        return int(number)
    return number


def _enum(widgets: list[Any], choices: tuple[str, ...]) -> str | None:
    text = _text(widgets)
    if text in choices:
        return text
    return None


def _checkbox(widgets: list[Any]) -> bool | None:
    if not widgets:
        return None
    raw = widgets[0].field_value
    if raw is None:
        return None
    text = str(raw).strip().lower()
    if text in _CHECK_ON:
        return True
    if text in _CHECK_OFF:
        return False
    return None


def _radio(widgets: list[Any], bands: tuple[tuple[float, str], ...]) -> str | None:
    selected = [
        widget
        for widget in widgets
        if str(widget.field_value or "").strip().lower() not in _RADIO_OFF
    ]
    if not selected:
        return None
    origin = selected[0].rect.x0
    center, label = min(bands, key=lambda band: abs(band[0] - origin))
    if abs(center - origin) > 80:
        return None
    return label


def _read_spec(spec: FieldSpec, groups: dict[str, list[Any]]) -> Any:
    if not spec.on_sheet:
        return None
    widgets = groups.get(spec.pdf_field, [])
    if spec.kind == "radio":
        return _radio(widgets, spec.bands)
    if spec.kind == "bool":
        return _checkbox(widgets)
    if spec.kind == "number":
        return _number(widgets)
    if spec.kind == "enum":
        return _enum(widgets, spec.choices)
    return _text(widgets)


def _number_warnings(groups: dict[str, list[Any]]) -> list[str]:
    warnings: list[str] = []
    for spec in SPECS:
        if spec.kind != "number":
            continue
        text = _text(groups.get(spec.pdf_field, []))
        if text is not None and _number(groups.get(spec.pdf_field, [])) is None:
            warnings.append(f"{spec.label} 的原文“{text}”不是数字，已留空。")
    return warnings


def read_collection_sheet(path: Path) -> dict[str, Any]:
    """读出全部字段。缺失的表单域对应值为 None。"""
    document = pymupdf.open(path)
    try:
        if document.page_count < 1 or not document.is_form_pdf:
            raise CollectionSheetNotFound(f"{path.name} 不是可填写的资料表 PDF。")
        groups: dict[str, list[Any]] = {}
        for widget in document[0].widgets() or []:
            groups.setdefault(widget.field_name, []).append(widget)
        if not SIGNATURE_FIELDS <= set(groups):
            raise CollectionSheetNotFound(f"{path.name} 不是 Design Data Collection Sheet。")
        values = {spec.key: _read_spec(spec, groups) for spec in SPECS}
        return {
            "source": str(path),
            "source_name": path.name,
            "values": values,
            "warnings": _number_warnings(groups),
        }
    finally:
        document.close()
