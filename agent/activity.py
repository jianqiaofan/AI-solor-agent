"""把正在进行的工作告诉页面。没有绑定时，报告会被丢掉。"""

from __future__ import annotations

import re
from contextvars import ContextVar
from typing import Callable

_report: ContextVar[Callable[[str], None] | None] = ContextVar("activity_report", default=None)

THINKING = "正在思考"
SAP_RUNNING = "正在调用SAP2000进行力学计算"
WEB_LOOKUP = "正在为您联网查询"
WIND_RUNNING = "正在计算风荷载"
SNOW_RUNNING = "正在计算雪荷载"
LOADS_RUNNING = "正在计算荷载"
LAYOUT_RUNNING = "正在布置主梁和立柱"
CAD_RUNNING = "正在绘制CAD图纸"
EXTRACT_RUNNING = "正在从资料提取设计参数"
UPDATE_RUNNING = "正在写入设计参数"

_WEB = (
    "web_search",
    "internet_search",
    "search_web",
    "websearch",
    "browse_web",
    "tavily",
    "duckduckgo",
    "bing_search",
    "google_search",
    "serper",
    "联网",
)


def bind_activity(fn: Callable[[str], None]):
    return _report.set(fn)


def reset_activity(token) -> None:
    _report.reset(token)


def report_activity(text: str) -> None:
    fn = _report.get()
    if fn is None or not text:
        return
    fn(text)


def load_activity(names: list[str]) -> str:
    wind = any(name.lower().startswith("wind") for name in names)
    snow = any(name.lower().startswith("snow") for name in names)
    if wind and not snow:
        return WIND_RUNNING
    if snow and not wind:
        return SNOW_RUNNING
    return LOADS_RUNNING


def activity_for_tool(name: str) -> str:
    folded = re.sub(r"[\s\-]+", "_", (name or "").strip().lower())
    if not folded:
        return ""
    if any(token in folded for token in _WEB):
        return WEB_LOOKUP
    if "sap" in folded:
        return SAP_RUNNING
    if folded.startswith("wind"):
        return WIND_RUNNING
    if folded.startswith("snow"):
        return SNOW_RUNNING
    if folded.startswith("moduledead") or folded == "dead" or "load" in folded:
        return LOADS_RUNNING
    return ""


def tool_names_from_chunk(chunk: object) -> list[str]:
    names: list[str] = []
    for attr in ("tool_call_chunks", "tool_calls"):
        for call in getattr(chunk, attr, None) or []:
            if isinstance(call, dict):
                name = call.get("name")
            else:
                name = getattr(call, "name", None)
            if name:
                names.append(str(name))
    return names
