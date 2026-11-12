"""用 LangChain 调用 DeepSeek。"""

from __future__ import annotations

from dataclasses import replace

from agent.settings import Settings

MODELS = ("deepseek-flash", "deepseek-v4-pro")
MAX_HISTORY = 40
SYSTEM_PROMPT = (
    "你是光伏跟踪支架设计助手，和结构工程师一起做设计。"
    "从资料里提取设计参数由系统按资料表完成，并写成当前项目成果目录里的 design_case.json。"
    "不要自己编造已经提取出的数值。没有调用荷载工具并拿到结果之前，不要说已经算过荷载。"
    "不要声称出过计算书。"
    "用中文回答，先给结论，再补充需要核对的地方。不知道就说不知道。"
)
_LOAD_GUIDE = (
    "计算风荷载或雪荷载时必须调用工具，不要心算。"
    "USA(ASCE7-16) 用 windASCE16 和 snowASCE16。"
    "Europe(Eurocode 1991-4) 用 windEN1991 和 snowEN1991。"
    "计算荷载时还要调用 moduleDead。"
    "它用组件重量、长度和宽度，把单块组件自重除以组件面积，得到 kN/m² 的面荷载。"
    "两本规范都用这一个工具。"
    "参数只用设计案例里已经写出的数值，或用户在当前这句话里明确给出的数值。"
    "案例里是 null、用户也没有给出的项，不要猜测。"
    "欧标风的地形类别，以及欧标雪的暴露条件 windswept、normal、sheltered，都不在资料表里。"
    "用户没有明确指定时先问。"
    "工具返回之前，不要说已经算完。返回之后用中文先给数值，再说明规范条款、分区和假设。"
)


def model_choices(current: str) -> list[str]:
    choices = list(MODELS)
    if current and current not in choices:
        choices.append(current)
    return choices


def resolve_model(requested: str | None, settings: Settings) -> str:
    allowed = set(model_choices(settings.model))
    if requested and requested in allowed:
        return requested
    return settings.model


def to_messages(
    history: list[dict],
    project_name: str = "",
    *,
    design_case: str | None = None,
    load_tools: bool = False,
    project_facts: bool = False,
) -> list:
    from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

    from agent.load_tools import design_code_of

    content = SYSTEM_PROMPT
    if project_name:
        content += (
            f"当前项目是「{project_name}」。"
            "只讨论这个项目，不要把其他项目的数据、结论或对话混进来。"
        )
    if load_tools:
        content += _LOAD_GUIDE
        code = design_code_of(design_case)
        if code:
            content += f"本项目的设计规范是 {code}。只调用这一本规范的荷载工具。"
        elif design_case:
            content += "设计案例里还没有 design_code。用户没有指定规范时，不要调用荷载工具。"
        else:
            content += "当前项目还没有 design_case.json。没有案例、用户也没有给出数值时，不要调用荷载工具。"
        if design_case:
            content += "当前项目的 design_case.json 如下：\n" + design_case
    elif project_facts:
        content += (
            "用户在了解这个项目已经记下的情况。"
            "只使用设计案例里写出的值，不要编造。"
            "值是 null 或空字符串时，说这项还没有。"
            "这个回答不会修改 design_case.json。不要说已经改过或写入了文件。"
            "不要把这次回答说成已经提取、已经改过参数、已经算过荷载或已经出过计算书。"
        )
        relative = f"projects/{project_name}/成果/design_case.json" if project_name else "design_case.json"
        if design_case:
            content += f"当前项目的 {relative} 如下：\n" + design_case
        else:
            content += f"还没有 {relative}。不要编造组件排布、桩埋深或其他设计参数。"
    messages: list = [SystemMessage(content=content)]
    for item in history[-MAX_HISTORY:]:
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        if item.get("role") == "assistant":
            messages.append(AIMessage(content=content))
        elif item.get("role") == "user":
            messages.append(HumanMessage(content=content))
    return messages


def chunk_text(chunk: object) -> str:
    content = getattr(chunk, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text") or ""))
        return "".join(parts)
    return ""


def explain(exc: Exception, settings: Settings | None = None) -> str:
    raw = str(exc).strip()
    if settings and settings.api_key:
        raw = raw.replace(settings.api_key, "…")
    lowered = raw.lower()
    if "401" in raw or "authentication" in lowered or "api key" in lowered:
        return "DeepSeek 没有接受这把密钥。请检查 .env 里的 DEEPSEEK_API_KEY 是否完整，保存后刷新此页。"
    if "402" in raw or "insufficient" in lowered:
        return "DeepSeek 账户余额不足，这次没有生成回复。"
    if "timeout" in lowered or "timed out" in lowered:
        return "模型响应超时。可以再发一次。"
    line = raw.splitlines()[0] if raw else exc.__class__.__name__
    if len(line) > 160:
        line = line[:160] + "…"
    return "没有收到模型回复：" + line


def build_model(
    settings: Settings,
    *,
    disable_thinking: bool,
    temperature: float = 0.6,
    timeout: int = 120,
    max_tokens: int = 4096,
    max_retries: int = 1,
):
    try:
        from langchain_deepseek import ChatDeepSeek
    except ImportError as exc:
        raise RuntimeError("还没有安装 langchain-deepseek。") from exc

    kwargs = {
        "model": settings.model,
        "api_key": settings.api_key,
        "api_base": settings.base_url,
        "temperature": temperature,
        "timeout": timeout,
        "max_retries": max_retries,
        "max_tokens": max_tokens,
    }
    if not disable_thinking:
        return ChatDeepSeek(**kwargs)
    try:
        return ChatDeepSeek(**kwargs, extra_body={"thinking": {"type": "disabled"}})
    except TypeError:
        return ChatDeepSeek(**kwargs)


def with_model(settings: Settings, model: str) -> Settings:
    return replace(settings, model=model)


_REWRITE_PROMPT = (
    "你在给结构工程师看一份刚从资料表提取出来的设计参数草稿。"
    "只用给定 JSON 里已经写明的值，不要编造，不要把 null 或空字符串说成已经有了。"
    "用中文，先说已经提取完成，再说明草稿文件的位置和状态是 draft。"
    "有值的参数用短句分组说清楚，空着的项只提一句还需要核对，不要逐条罗列。"
    "确认之前不会拿这份草稿去算荷载，也不要声称已经出过计算书。"
)


def rewrite_extraction_reply(settings: Settings, user_text: str, relative_path: str, case_json: str) -> str:
    from langchain_core.messages import HumanMessage, SystemMessage

    messages = [
        SystemMessage(content=_REWRITE_PROMPT),
        HumanMessage(
            content=(
                f"用户说：{user_text}\n\n"
                f"草稿文件：{relative_path}\n\n"
                f"{case_json}"
            )
        ),
    ]
    try:
        reply = _rewrite_invoke(settings, messages, disable_thinking=True)
    except Exception as exc:
        if not _rewrite_thinking_rejected(exc):
            raise
        reply = _rewrite_invoke(settings, messages, disable_thinking=False)
    text = chunk_text(reply).strip()
    if not text:
        raise RuntimeError("模型没有改写出说明。")
    return text


def _rewrite_invoke(settings: Settings, messages: list, *, disable_thinking: bool):
    model = build_model(
        settings,
        disable_thinking=disable_thinking,
        temperature=0.3,
        timeout=60,
        max_tokens=1200,
        max_retries=0,
    )
    return model.invoke(messages)


def _rewrite_thinking_rejected(exc: Exception) -> bool:
    text = str(exc).lower()
    return "thinking" in text and any(code in text for code in ("400", "422", "invalid"))
