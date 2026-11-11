"""用模型判断这句话要不要提取设计参数。"""

from __future__ import annotations

import json

from agent.chat import build_model, chunk_text
from agent.settings import Settings

EXTRACT = "extract_design_parameters"
WIND = "calculate_wind"
SNOW = "calculate_snow"
LOADS = "calculate_loads"
UPDATE = "update_parameters"
CHAT = "chat"
LOAD_INTENTS = (WIND, SNOW, LOADS)

_PROMPT = (
    "你是意图分类器。不要回答用户，不要摘取或编造任何设计数值。"
    "只输出一个 JSON 对象，不要代码块，不要解释。"
    "要系统去阅读当前项目已经提交的资料，并从中找出设计参数或指标时，"
    '输出 {"intent":"extract_design_parameters"}。'
    "提取设计参数、仔细阅读提交文件并找出设计指标、从资料表整理设计指标，都算要提取。"
    "要计算风荷载、风压、速度风压时，"
    '输出 {"intent":"calculate_wind"}。'
    "要计算雪荷载、雪压时，"
    '输出 {"intent":"calculate_snow"}。'
    "风和雪一起算，或只说计算作用荷载、计算荷载时，"
    '输出 {"intent":"calculate_loads"}。'
    "用户正在补充刚才计算所缺的时距、地形类别或暴露条件，按刚才要算的那一种输出。"
    "用户要补全或修改设计案例里的计算参数，例如时距、地形类别、暴露条件、风速、雪荷载、"
    "风险类别、组件尺寸或离地高度，而这句没有要求现在就计算时，"
    '输出 {"intent":"update_parameters"}。'
    "既要改参数又要计算时，按要计算的那一种输出。"
    "只问某个词的含义、还没让算、不要提取、以及和这些都无关的话，"
    '输出 {"intent":"chat"}。'
    "既要提取又要计算时，按提取输出。"
)


def parse_intent(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`").strip()
        if text.lower().startswith("json"):
            text = text[4:].strip()
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return CHAT
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return CHAT
    if isinstance(data, dict) and data.get("intent") in (EXTRACT, WIND, SNOW, LOADS, UPDATE):
        return str(data["intent"])
    return CHAT


def classify_intent(settings: Settings, text: str) -> str:
    from langchain_core.messages import HumanMessage, SystemMessage

    messages = [SystemMessage(content=_PROMPT), HumanMessage(content=text)]
    try:
        reply = _invoke(settings, messages, disable_thinking=True)
    except Exception as exc:
        if not _thinking_rejected(exc):
            raise
        reply = _invoke(settings, messages, disable_thinking=False)
    return parse_intent(chunk_text(reply))


def _invoke(settings: Settings, messages: list, *, disable_thinking: bool):
    model = build_model(
        settings,
        disable_thinking=disable_thinking,
        temperature=0,
        timeout=25,
        max_tokens=80,
        max_retries=0,
    )
    return model.invoke(messages)


def _thinking_rejected(exc: Exception) -> bool:
    text = str(exc).lower()
    return "thinking" in text and any(code in text for code in ("400", "422", "invalid"))
