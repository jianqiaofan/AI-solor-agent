"""用模型判断这句话要提取参数、算荷载、改参数，还是只布置支架线模。"""

from __future__ import annotations

import json

from agent.chat import build_model, chunk_text
from agent.settings import Settings

EXTRACT = "extract_design_parameters"
WIND = "calculate_wind"
SNOW = "calculate_snow"
LOADS = "calculate_loads"
UPDATE = "update_parameters"
DESIGN = "design_line_model"
SAP = "run_sap2000"
CAD = "draw_cad"
INQUIRE = "inquire_project"
CHAT = "chat"
LOAD_INTENTS = (WIND, SNOW, LOADS)
_PROJECT_FACTS = (
    "组件排布",
    "排布",
    "桩埋深",
    "埋深",
    "桩入土",
    "入土深度",
    "项目情况",
    "哪些参数",
    "什么参数",
    "组件尺寸",
    "组件长度",
    "组件宽度",
    "离地高度",
    "组件朝向",
    "这个项目",
    "本项目",
    "当前项目",
)

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
    "要调用 SAP2000、做结构计算或计算内力时，"
    '输出 {"intent":"run_sap2000"}。'
    "要查看或展示已经算好的力学结果、结构计算结果、应力比或内力时，"
    '也输出 {"intent":"run_sap2000"}。'
    "这是在看已有结果。用户明确说重新力学计算、重新计算内力或重新调用 SAP2000 时，同样输出这一项。"
    "没有线模或荷载时也按这一项输出，不要改成只算荷载或只出线模。"
    "只算风、雪或荷载，没有要求 SAP2000、结构计算或内力时，不要输出 run_sap2000。"
    "既要提取又要调用 SAP2000 时，按提取输出。"
    "要设计支架、建立支架线模，或只要主梁和立柱的线模时，"
    '输出 {"intent":"design_line_model"}。'
    "这一步只布置线模。选截面、加荷载、运行 SAP2000 和出计算书都不要当成这一项。"
    "既要提取又要设计时，按提取输出。既要计算荷载又要设计时，按要计算的那一种输出。"
    "既要改参数又要设计时，按设计输出。"
    "要生成 CAD 图纸、打开 CAD，或把线模画到图纸上时，"
    '输出 {"intent":"draw_cad"}。'
    "这一步只打开 CAD，画出线模并标注尺寸。没有线模时仍按这一项输出，不要改成设计线模。"
    "只问 CAD 或图纸的含义、还没让画时，不要输出 draw_cad。"
    "既要提取又要出图时，按提取输出。既要计算荷载又要出图时，按要计算的那一种输出。"
    "既要调用 SAP2000 又要出图时，按 SAP2000 输出。既要设计线模又要出图时，按出图输出。"
    "用户在了解当前项目已经记下的情况，例如组件排布、桩的埋深、离地高度、组件尺寸、朝向，"
    "或问这个项目现在是什么情况时，"
    '输出 {"intent":"inquire_project"}。'
    "这是在问设计案例里已经有的内容，不是要求从资料重新提取，也不是改数值、计算荷载或设计支架。"
    "既要了解情况又要提取时，按提取输出。既要了解情况又要计算时，按要计算的那一种输出。"
    "既要了解情况又要改参数时，按改参数输出。既要了解情况又要设计支架时，按设计输出。"
    "只问某个词的含义、还没让算、不要提取、不要设计、不是在问这个项目的情况，以及和这些都无关的话，"
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
    if isinstance(data, dict) and data.get("intent") in (
        EXTRACT,
        WIND,
        SNOW,
        LOADS,
        UPDATE,
        DESIGN,
        SAP,
        CAD,
        INQUIRE,
    ):
        return str(data["intent"])
    return CHAT


def asks_about_project(text: str) -> bool:
    """这句话是在问当前项目已经记下的情况，而不是在解释一个词。"""
    if "项目" not in text and any(word in text for word in ("什么是", "啥是", "何谓", "什么意思", "含义")):
        return False
    return any(phrase in text for phrase in _PROJECT_FACTS)


def resolve_project_inquiry(intent: str, text: str) -> str:
    """了解项目情况时交给带设计案例的对话。提取、改参数、算荷载和设计优先。"""
    if intent in LOAD_INTENTS or intent in (EXTRACT, DESIGN, UPDATE, SAP, CAD):
        return intent
    if any(word in text for word in ("计算", "算一下", "算风", "算雪", "算荷载")):
        if intent == INQUIRE:
            wind = "风" in text
            snow = "雪" in text
            if wind and snow:
                return LOADS
            if snow and not wind:
                return SNOW
            if wind and not snow:
                return WIND
            return LOADS
        return intent
    if any(phrase in text for phrase in ("提取设计", "找出设计指标", "阅读提交", "从资料表")):
        return EXTRACT
    if intent == INQUIRE or asks_about_project(text):
        return INQUIRE
    return intent


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
