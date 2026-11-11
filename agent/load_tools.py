"""把四本规范里的风、雪工具交给设计助手调用。"""

from __future__ import annotations

import json
import logging
import sys
from typing import Any

from agent.settings import ROOT

logger = logging.getLogger("agent")

_ASCE = "USA(ASCE7-16)"
_EN = "Europe(Eurocode 1991-4)"
_EXPECTED = {
    "windASCE16": _ASCE,
    "snowASCE16": _ASCE,
    "windEN1991": _EN,
    "snowEN1991": _EN,
}
_MAX_ROUNDS = 4


def design_code_of(case_json: str | None) -> str | None:
    if not case_json:
        return None
    try:
        data = json.loads(case_json)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    site = data.get("site") if isinstance(data.get("site"), dict) else {}
    code = site.get("design_code") or data.get("code_pack")
    if isinstance(code, str) and code:
        return code
    return None


def calculation_tools() -> list[Any]:
    from langchain_core.tools import tool

    return [tool(fn) for fn in _functions().values()]


def run_load_tool(name: str, args: dict[str, Any], design_code: str | None) -> dict[str, Any]:
    expected = _EXPECTED.get(name)
    if expected is None:
        return {"error": f"没有名为 {name} 的荷载工具。"}
    if design_code and design_code != expected:
        return {
            "error": f"当前项目规范是 {design_code}。这一步只能使用 {expected} 的工具。",
        }
    try:
        return _functions()[name](**args)
    except (TypeError, ValueError) as exc:
        return {"error": str(exc)}


async def stream_with_load_tools(
    settings,
    messages: list,
    request,
    *,
    design_code: str | None,
    disable_thinking: bool,
):
    from agent.chat import build_model, chunk_text

    tools = calculation_tools()
    model = build_model(settings, disable_thinking=disable_thinking).bind_tools(tools)
    working = list(messages)
    for _ in range(_MAX_ROUNDS):
        if await request.is_disconnected():
            return
        reply = await model.ainvoke(working)
        calls = list(getattr(reply, "tool_calls", None) or [])
        if not calls:
            text = chunk_text(reply).strip()
            if text:
                yield text
            return
        working.append(reply)
        for call in calls:
            working.append(_tool_message(call, design_code))
    yield "荷载工具反复调用，这次没有整理成说明。"


def _tool_message(call: dict[str, Any], design_code: str | None):
    from langchain_core.messages import ToolMessage

    name = str(call.get("name") or "")
    args = call.get("args") or {}
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except json.JSONDecodeError:
            args = {}
    if not isinstance(args, dict):
        args = {}
    logger.info("load tool %s", name)
    payload = run_load_tool(name, args, design_code)
    return ToolMessage(
        content=json.dumps(payload, ensure_ascii=False),
        tool_call_id=str(call.get("id") or name),
    )


def _functions() -> dict[str, Any]:
    _ensure_loads_path()
    from loads.tools.code_loads import snowASCE16, snowEN1991, windASCE16, windEN1991

    return {
        "windASCE16": windASCE16,
        "snowASCE16": snowASCE16,
        "windEN1991": windEN1991,
        "snowEN1991": snowEN1991,
    }


def _ensure_loads_path() -> None:
    package_root = str(ROOT / "subsystems" / "loads_sap2000")
    if package_root not in sys.path:
        sys.path.insert(0, package_root)
