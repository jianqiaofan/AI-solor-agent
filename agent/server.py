"""设计助手的本地页面和对话接口。"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from agent.beam_layout import layout_view
from agent.extract import ExtractionError, extract_project_materials
from agent.intent import CHAT, EXTRACT, LOAD_INTENTS, UPDATE, classify_intent
from agent.load_check import (
    answer_load_request,
    answer_parameter_update,
    resolve_load_follow_up,
    resolve_parameter_edit,
)
from agent.chat import (
    build_model,
    chunk_text,
    explain,
    model_choices,
    resolve_model,
    rewrite_extraction_reply,
    to_messages,
    with_model,
)
from agent.settings import (
    DATA_DIR,
    ROOT,
    STATIC_DIR,
    ConfigError,
    reload_env,
    require_settings,
)
from agent.store import (
    MAX_MATERIAL_BYTES,
    ConversationNotFound,
    MaterialError,
    ProjectExists,
    ProjectNameError,
    ProjectNotFound,
    RESULTS_DIR,
    Store,
)

logger = logging.getLogger("agent")
store = Store(DATA_DIR / "assistant.db", projects_root=ROOT / "projects")
_busy: set[str] = set()
_busy_lock = threading.Lock()
MAX_CHARS = 20000


class ChatRequest(BaseModel):
    project_id: str | None = None
    conversation_id: str | None = None
    text: str = ""
    model: str | None = None


class ProjectRequest(BaseModel):
    name: str = ""


class OpenFileRequest(BaseModel):
    path: str = ""


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    reload_env()
    yield


app = FastAPI(title="设计助手", lifespan=_lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def index() -> HTMLResponse:
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    try:
        payload = store.list_projects()
    except Exception:
        logging.exception("list projects for index")
        payload = []
    blob = (
        json.dumps(payload, ensure_ascii=False)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
    )
    marker = '<script id="boot-projects" type="application/json">[]</script>'
    html = html.replace(
        marker,
        f'<script id="boot-projects" type="application/json">{blob}</script>',
        1,
    )
    return HTMLResponse(html, headers={"Cache-Control": "no-store"})


@app.get("/api/meta")
def meta() -> dict:
    reload_env()
    try:
        settings = require_settings()
        current = settings.model
        ready = True
    except ConfigError:
        current = "deepseek-flash"
        ready = False
    return {"ready": ready, "model": current, "models": model_choices(current)}


@app.get("/api/projects")
def list_projects(response: Response) -> dict:
    response.headers["Cache-Control"] = "no-store"
    return {"projects": store.list_projects()}


@app.post("/api/projects")
def create_project(body: ProjectRequest):
    try:
        return store.create_project(body.name)
    except ProjectNameError as exc:
        return _fail(400, str(exc))
    except ProjectExists:
        return _fail(409, "已经有同名项目。")
    except OSError:
        return _fail(400, "项目目录没有建成，请换一个名称再试。")


@app.get("/api/projects/{project_id}/layout")
def project_layout(project_id: str):
    try:
        workspace = store.list_workspace(project_id)
    except ProjectNotFound:
        return _fail(404, "没有这个项目。")
    case_path = ROOT / workspace["path"] / RESULTS_DIR / "design_case.json"
    if not case_path.is_file():
        return {"ready": False, "message": "还没有设计案例。先从资料里提取参数，才能画主梁和立柱。"}
    try:
        data = json.loads(case_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"ready": False, "message": "设计案例没有读出来。"}
    geometry = data.get("geometry") if isinstance(data, dict) else None
    if not isinstance(geometry, dict):
        return {"ready": False, "message": "设计案例里没有几何参数。"}
    return layout_view(geometry)


@app.get("/api/projects/{project_id}/files")
def list_project_files(project_id: str):
    try:
        return store.list_workspace(project_id)
    except ProjectNotFound:
        return _fail(404, "没有这个项目。")


@app.post("/api/projects/{project_id}/materials")
async def add_materials(project_id: str, files: list[UploadFile] = File(...)):
    if not files:
        return _fail(400, "请选择文件。")
    saved = 0
    message = ""
    try:
        for upload in files:
            try:
                content = await _read_upload(upload)
                store.save_material(project_id, upload.filename or "", content)
                saved += 1
            except MaterialError as exc:
                message = str(exc)
    except ProjectNotFound:
        return _fail(404, "没有这个项目。")
    if saved == 0:
        return _fail(400, message or "请选择文件。")
    payload = store.list_workspace(project_id)
    if message:
        payload["message"] = message
    return payload


@app.post("/api/projects/{project_id}/open")
def open_project_file(project_id: str, body: OpenFileRequest):
    try:
        target = store.resolve_workspace_file(project_id, body.path)
    except ProjectNotFound:
        return _fail(404, "没有这个项目。")
    except FileNotFoundError:
        return _fail(404, "没有这个文件。")
    try:
        os.startfile(target)  # noqa: S606  只打开当前项目目录里的文件
    except OSError:
        return _fail(400, "这个文件没有打开。")
    return {"ok": True}


@app.delete("/api/projects/{project_id}/files")
def delete_project_file(project_id: str, body: OpenFileRequest):
    try:
        store.delete_workspace_file(project_id, body.path)
    except ProjectNotFound:
        return _fail(404, "没有这个项目。")
    except FileNotFoundError:
        return _fail(404, "没有这个文件。")
    except OSError:
        return _fail(400, "这个文件没有删掉。")
    return store.list_workspace(project_id)


@app.delete("/api/projects/{project_id}")
def delete_project(project_id: str):
    if not store.delete_project(project_id):
        return _fail(404, "没有这个项目。")
    return {"ok": True}


@app.get("/api/conversations")
def list_conversations(project_id: str = "") -> dict:
    if not project_id:
        return {"conversations": []}
    return {"conversations": store.list_summaries(project_id)}


@app.get("/api/conversations/{conversation_id}")
def get_conversation(conversation_id: str):
    found = store.get(conversation_id)
    if found is None:
        return _fail(404, "没有这则对话。")
    return found


@app.delete("/api/conversations/{conversation_id}")
def delete_conversation(conversation_id: str):
    if not store.delete(conversation_id):
        return _fail(404, "没有这则对话。")
    return {"ok": True}


@app.post("/api/chat")
async def chat(body: ChatRequest, request: Request):
    reload_env()
    text = body.text.strip()
    if not text:
        return _fail(400, "请先输入内容。")
    if len(text) > MAX_CHARS:
        return _fail(400, "这条消息太长了。请分成几段发送。")
    try:
        settings = require_settings()
    except ConfigError as exc:
        return _fail(400, str(exc))
    settings = with_model(settings, resolve_model(body.model, settings))

    if not (body.project_id or "").strip():
        return _fail(400, "请先新建并选中一个项目。")
    with _busy_lock:
        if body.conversation_id and body.conversation_id in _busy:
            return _fail(409, "上一条还在回复。")
    try:
        summary = store.start_turn(body.project_id or "", body.conversation_id, text)
    except ProjectNotFound:
        return _fail(404, "没有这个项目。")
    except ConversationNotFound:
        return _fail(404, "没有这则对话。")

    conversation_id = summary["id"]
    with _busy_lock:
        _busy.add(conversation_id)

    async def events():
        try:
            async for piece in replies():
                yield piece
        finally:
            with _busy_lock:
                _busy.discard(conversation_id)

    async def replies():
        try:
            intent = await asyncio.to_thread(classify_intent, settings, text)
        except Exception:
            logger.exception("intent classification failed")
            intent = "chat"
        logger.info("intent %s", intent)
        if intent in LOAD_INTENTS or intent in (CHAT, UPDATE):
            history = store.get(conversation_id)
            prior = history["messages"] if history else []
            intent = resolve_load_follow_up(intent, prior)
            intent = resolve_parameter_edit(intent, text)
            logger.info("intent after follow-up %s", intent)
        if intent == EXTRACT:
            async for piece in _extraction_events(
                body.project_id or "",
                conversation_id,
                summary,
                settings,
                text,
            ):
                yield piece
            return
        if intent == UPDATE:
            async for piece in _parameter_events(
                conversation_id,
                summary,
            ):
                yield piece
            return
        if intent in LOAD_INTENTS:
            async for piece in _load_events(
                conversation_id,
                summary,
                intent,
            ):
                yield piece
            return
        parts: list[str] = []
        try:
            yield _sse({"type": "meta", "conversation": summary})
            history = store.get(conversation_id)
            if history is None:
                raise ConversationNotFound(conversation_id)
            project_name = summary.get("project_name", "")
            messages = to_messages(history["messages"], project_name)
            try:
                async for piece in _stream(settings, messages, request):
                    parts.append(piece)
                    yield _sse({"type": "delta", "text": piece})
            except Exception as exc:
                if parts or not _thinking_rejected(exc):
                    raise
                logger.info("thinking 开关未被接受，改为默认模式重试")
                async for piece in _stream(settings, messages, request, disable_thinking=False):
                    parts.append(piece)
                    yield _sse({"type": "delta", "text": piece})
            answer = "".join(parts).strip()
            if answer:
                store.append_assistant(conversation_id, answer)
            if await request.is_disconnected():
                return
            yield _sse({"type": "done"})
        except Exception as exc:
            logger.exception("model call failed")
            answer = "".join(parts).strip()
            if answer:
                store.append_assistant(conversation_id, answer)
            if await request.is_disconnected():
                return
            yield _sse({"type": "error", "message": explain(exc, settings)})

    return StreamingResponse(
        events(),
        media_type="text/event-stream; charset=utf-8",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _extraction_events(
    project_id: str,
    conversation_id: str,
    summary: dict,
    settings,
    user_text: str,
):
    try:
        yield _sse({"type": "meta", "conversation": summary})
        try:
            answer, wrote = await asyncio.to_thread(extract_project_materials, store, project_id)
        except ExtractionError as exc:
            answer, wrote = str(exc), False
        except Exception:
            logger.exception("extract failed")
            answer, wrote = "资料没有提取出来。", False
        if wrote:
            answer = await _friendly_answer(settings, user_text, summary, answer)
        store.append_assistant(conversation_id, answer)
        yield _sse({"type": "delta", "text": answer})
        yield _sse({"type": "done", "refresh_files": wrote})
    finally:
        with _busy_lock:
            _busy.discard(conversation_id)


async def _friendly_answer(settings, user_text: str, summary: dict, fallback: str) -> str:
    project_name = str(summary.get("project_name") or "").strip()
    if not project_name:
        return fallback
    relative = f"projects/{project_name}/成果/design_case.json"
    path = ROOT / relative
    try:
        case_json = path.read_text(encoding="utf-8")
    except OSError:
        logger.exception("design_case.json 没有读出来")
        return fallback
    try:
        return await asyncio.to_thread(
            rewrite_extraction_reply,
            settings,
            user_text,
            relative,
            case_json,
        )
    except Exception:
        logger.exception("friendly extraction reply failed")
        return fallback


async def _parameter_events(conversation_id: str, summary: dict):
    yield _sse({"type": "meta", "conversation": summary})
    history = store.get(conversation_id)
    messages = history["messages"] if history else []
    project_name = str(summary.get("project_name") or "")
    try:
        answer, wrote = await asyncio.to_thread(
            answer_parameter_update,
            _design_case_text(project_name),
            project_name,
            messages,
            _design_case_path(project_name),
        )
    except Exception:
        logger.exception("design case update failed")
        answer, wrote = "设计参数没有写入。", False
    store.append_assistant(conversation_id, answer)
    yield _sse({"type": "delta", "text": answer})
    yield _sse({"type": "done", "refresh_files": wrote})


async def _load_events(conversation_id: str, summary: dict, intent: str):
    yield _sse({"type": "meta", "conversation": summary})
    history = store.get(conversation_id)
    messages = history["messages"] if history else []
    project_name = str(summary.get("project_name") or "")
    try:
        answer, wrote = await asyncio.to_thread(
            answer_load_request,
            intent,
            _design_case_text(project_name),
            project_name,
            messages,
            _design_case_path(project_name),
        )
    except Exception:
        logger.exception("load check failed")
        answer, wrote = "荷载没有算成。", False
    store.append_assistant(conversation_id, answer)
    yield _sse({"type": "delta", "text": answer})
    yield _sse({"type": "done", "refresh_files": wrote})


def _design_case_path(project_name: str):
    name = (project_name or "").strip()
    if not name:
        return None
    return store.projects_root / name / RESULTS_DIR / "design_case.json"


def _design_case_text(project_name: str) -> str | None:
    path = _design_case_path(project_name)
    if path is None:
        return None
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


async def _stream(settings, messages, request: Request, *, disable_thinking: bool = True):
    model = build_model(settings, disable_thinking=disable_thinking)
    async for chunk in model.astream(messages):
        if await request.is_disconnected():
            break
        piece = chunk_text(chunk)
        if piece:
            yield piece


def _thinking_rejected(exc: Exception) -> bool:
    text = str(exc).lower()
    return "thinking" in text and any(code in text for code in ("400", "422", "invalid"))


def _sse(payload: dict) -> str:
    return "data: " + json.dumps(payload, ensure_ascii=False) + "\n\n"


async def _read_upload(upload: UploadFile) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        block = await upload.read(1024 * 1024)
        if not block:
            break
        total += len(block)
        if total > MAX_MATERIAL_BYTES:
            raise MaterialError("单个文件请不要超过 100 MB。")
        chunks.append(block)
    return b"".join(chunks)


def _fail(status: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"message": message})
