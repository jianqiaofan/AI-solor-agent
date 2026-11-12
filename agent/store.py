"""把项目和对话记在本机 SQLite 里，重新打开还在。"""

from __future__ import annotations

import json
import re
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

_ID = re.compile(r"^[a-f0-9]{12}$")


class ConversationNotFound(KeyError):
    pass


class ProjectNotFound(KeyError):
    pass


class ProjectExists(Exception):
    pass


class ProjectNameError(ValueError):
    pass


class MaterialError(ValueError):
    pass


_INVALID_NAME = '<>:"/\\|?*'
_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}
MATERIALS_DIR = "资料"
RESULTS_DIR = "成果"
MAX_MATERIAL_BYTES = 100 * 1024 * 1024


def title_from_text(text: str) -> str:
    line = " ".join(text.strip().split())
    if not line:
        return "新对话"
    if len(line) <= 22:
        return line
    return line[:22] + "…"


class Store:
    def __init__(self, path: Path, projects_root: Path | None = None) -> None:
        self.path = path
        self.projects_root = projects_root or path.parent / "projects"
        self._lock = threading.Lock()
        imported = None
        with self._lock, self._session() as connection:
            _create_schema(connection)
            imported = self._import_json(connection)
        if imported is not None:
            try:
                imported.replace(imported.with_name("conversations.json.imported"))
            except OSError:
                return

    def list_projects(self) -> list[dict]:
        with self._lock, self._session() as connection:
            rows = connection.execute(
                "SELECT * FROM projects ORDER BY updated_at DESC"
            ).fetchall()
            projects = []
            for row in rows:
                project = _project_from_row(row)
                try:
                    if self._ensure_workspace(project):
                        connection.execute(
                            "UPDATE projects SET path = ? WHERE id = ?",
                            (project["path"], project["id"]),
                        )
                except OSError:
                    pass
                projects.append(_project_summary(project))
            return projects

    def create_project(self, name: str) -> dict:
        cleaned = _clean_name(name)
        project = _blank_project(cleaned)
        with self._lock, self._session() as connection:
            if _project_named(connection, cleaned) is not None:
                raise ProjectExists(cleaned)
            self._ensure_workspace(project)
            _insert_project(connection, project)
        return _project_summary(project)

    def list_workspace(self, project_id: str) -> dict:
        if not _ID.fullmatch(project_id or ""):
            raise ProjectNotFound(project_id)
        with self._lock, self._session() as connection:
            project = _project_by_id(connection, project_id)
            if project is None:
                raise ProjectNotFound(project_id)
            try:
                if self._ensure_workspace(project):
                    connection.execute(
                        "UPDATE projects SET path = ? WHERE id = ?",
                        (project["path"], project["id"]),
                    )
            except OSError:
                pass
            name = project["name"]
            relative = project.get("path", "")
        root = (self.projects_root / name).resolve()
        folders = []
        for folder_name in (MATERIALS_DIR, RESULTS_DIR):
            folder = (root / folder_name).resolve()
            files: list[dict] = []
            if folder.is_dir() and _is_inside(folder, root):
                self._append_workspace_files(folder, folder, root, files)
            folders.append({"name": folder_name, "files": files})
        return {"path": relative, "folders": folders}

    def _append_workspace_files(
        self,
        folder: Path,
        top: Path,
        root: Path,
        files: list[dict],
    ) -> None:
        if len(files) >= 200:
            return
        for item in sorted(folder.iterdir(), key=lambda path: path.name):
            if item.name.startswith("~$") or item.name.endswith(".uploading"):
                continue
            resolved = item.resolve()
            if not _is_inside(resolved, root):
                continue
            if item.is_dir() and item.name in {"sap", "SAP2000"} and folder == top:
                record = self._file_record(item, top)
                record["directory"] = True
                files.append(record)
                continue
            if item.is_dir():
                self._append_workspace_files(item, top, root, files)
                continue
            if item.is_file():
                files.append(self._file_record(item, top))
            if len(files) >= 200:
                return

    def _file_record(self, item: Path, top: Path) -> dict:
        resolved = item.resolve()
        return {
            "name": item.relative_to(top).as_posix(),
            "path": resolved.relative_to(self.projects_root.parent).as_posix(),
        }

    def save_material(self, project_id: str, filename: str, content: bytes) -> dict:
        if not _ID.fullmatch(project_id or ""):
            raise ProjectNotFound(project_id)
        name = _clean_filename(filename)
        if len(content) > MAX_MATERIAL_BYTES:
            raise MaterialError("单个文件请不要超过 100 MB。")
        with self._lock, self._session() as connection:
            project = _project_by_id(connection, project_id)
            if project is None:
                raise ProjectNotFound(project_id)
            try:
                if self._ensure_workspace(project):
                    connection.execute(
                        "UPDATE projects SET path = ? WHERE id = ?",
                        (project["path"], project["id"]),
                    )
            except OSError as exc:
                raise MaterialError("资料目录没有建成。") from exc
            project_name = project["name"]
        folder = (self.projects_root / project_name / MATERIALS_DIR).resolve()
        target = (folder / name).resolve()
        if not _is_inside(target, folder):
            raise MaterialError("这个文件名不能使用。")
        replaced = target.exists()
        temporary = folder / f".{name}.uploading"
        try:
            temporary.write_bytes(content)
            temporary.replace(target)
        except OSError as exc:
            temporary.unlink(missing_ok=True)
            raise MaterialError("这个文件没有放进去。") from exc
        return {"name": name, "replaced": replaced}

    def resolve_workspace_file(
        self,
        project_id: str,
        relative: str,
        allow_directory: bool = False,
    ) -> Path:
        if not _ID.fullmatch(project_id or ""):
            raise ProjectNotFound(project_id)
        parts = Path(relative or "").parts
        if not relative or relative.startswith(("/", "\\")) or ".." in parts:
            raise FileNotFoundError(relative)
        with self._lock, self._session() as connection:
            project = _project_by_id(connection, project_id)
            if project is None:
                raise ProjectNotFound(project_id)
            name = project["name"]
        root = (self.projects_root / name).resolve()
        candidate = (self.projects_root.parent / relative).resolve()
        if not candidate.is_file() and not (allow_directory and candidate.is_dir()):
            raise FileNotFoundError(relative)
        if not _is_inside(candidate, root):
            raise FileNotFoundError(relative)
        return candidate

    def delete_workspace_file(self, project_id: str, relative: str) -> None:
        target = self.resolve_workspace_file(project_id, relative)
        try:
            target.unlink()
        except OSError as exc:
            raise OSError("这个文件没有删掉。") from exc

    def delete_project(self, project_id: str) -> bool:
        if not _ID.fullmatch(project_id or ""):
            return False
        with self._lock, self._session() as connection:
            cursor = connection.execute("DELETE FROM projects WHERE id = ?", (project_id,))
            return cursor.rowcount > 0

    def list_summaries(self, project_id: str) -> list[dict]:
        if not _ID.fullmatch(project_id or ""):
            return []
        with self._lock, self._session() as connection:
            project = _project_by_id(connection, project_id)
            if project is None:
                return []
            rows = connection.execute(
                """
                SELECT * FROM conversations
                WHERE project_id = ?
                ORDER BY updated_at DESC
                """,
                (project_id,),
            ).fetchall()
            return [_summary(_conversation_from_row(row), project["name"]) for row in rows]

    def get(self, conversation_id: str) -> dict | None:
        self._ensure_id(conversation_id)
        with self._lock, self._session() as connection:
            return _load_conversation(connection, conversation_id)

    def delete(self, conversation_id: str) -> bool:
        if not _ID.fullmatch(conversation_id or ""):
            return False
        with self._lock, self._session() as connection:
            cursor = connection.execute(
                "DELETE FROM conversations WHERE id = ?",
                (conversation_id,),
            )
            return cursor.rowcount > 0

    def start_turn(self, project_id: str, conversation_id: str | None, text: str) -> dict:
        message = text.strip()
        if not message:
            raise ValueError("empty message")
        self._ensure_id(project_id)
        with self._lock, self._session() as connection:
            project = _project_by_id(connection, project_id)
            if project is None:
                raise ProjectNotFound(project_id)
            if conversation_id is None:
                conversation = _blank(project_id)
                _insert_conversation(connection, conversation)
            else:
                self._ensure_id(conversation_id)
                conversation = _load_conversation(connection, conversation_id)
                if conversation is None or conversation.get("project_id") != project_id:
                    raise ConversationNotFound(conversation_id)
            now = _now()
            if not conversation["messages"]:
                conversation["title"] = title_from_text(message)
                connection.execute(
                    "UPDATE conversations SET title = ? WHERE id = ?",
                    (conversation["title"], conversation["id"]),
                )
            connection.execute(
                """
                INSERT INTO messages (conversation_id, role, content, created_at)
                VALUES (?, 'user', ?, ?)
                """,
                (conversation["id"], message, now),
            )
            connection.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?",
                (now, conversation["id"]),
            )
            connection.execute(
                "UPDATE projects SET updated_at = ? WHERE id = ?",
                (now, project["id"]),
            )
            conversation["updated_at"] = now
            return _summary(conversation, project["name"])

    def append_assistant(self, conversation_id: str, text: str) -> None:
        message = text.strip()
        if not message:
            return
        self._ensure_id(conversation_id)
        with self._lock, self._session() as connection:
            row = connection.execute(
                "SELECT id FROM conversations WHERE id = ?",
                (conversation_id,),
            ).fetchone()
            if row is None:
                raise ConversationNotFound(conversation_id)
            now = _now()
            connection.execute(
                """
                INSERT INTO messages (conversation_id, role, content, created_at)
                VALUES (?, 'assistant', ?, ?)
                """,
                (conversation_id, message, now),
            )
            connection.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?",
                (now, conversation_id),
            )

    def _ensure_id(self, conversation_id: str) -> None:
        if not _ID.fullmatch(conversation_id or ""):
            raise ConversationNotFound(conversation_id)

    @contextmanager
    def _session(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _import_json(self, connection: sqlite3.Connection) -> Path | None:
        count = connection.execute("SELECT COUNT(*) AS n FROM projects").fetchone()["n"]
        if count:
            return None
        json_path = self.path.with_name("conversations.json")
        if not json_path.is_file() or json_path.resolve() == self.path.resolve():
            return None
        try:
            loaded = json.loads(json_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(loaded, dict):
            return None
        for project in loaded.get("projects") or []:
            if not isinstance(project, dict) or not _ID.fullmatch(project.get("id") or ""):
                continue
            name = project.get("name") or ""
            if not name:
                continue
            _insert_project(
                connection,
                {
                    "id": project["id"],
                    "name": name,
                    "path": project.get("path") or "",
                    "created_at": project.get("created_at") or _now(),
                    "updated_at": project.get("updated_at") or _now(),
                },
                ignore=True,
            )
        for conversation in loaded.get("conversations") or []:
            if not isinstance(conversation, dict) or not _ID.fullmatch(conversation.get("id") or ""):
                continue
            project_id = conversation.get("project_id") or ""
            if _project_by_id(connection, project_id) is None:
                continue
            _insert_conversation(
                connection,
                {
                    "id": conversation["id"],
                    "project_id": project_id,
                    "title": conversation.get("title") or "新对话",
                    "created_at": conversation.get("created_at") or _now(),
                    "updated_at": conversation.get("updated_at") or _now(),
                    "messages": [],
                },
                ignore=True,
            )
            for message in conversation.get("messages") or []:
                if not isinstance(message, dict):
                    continue
                content = message.get("content") or ""
                role = message.get("role") or ""
                if role not in {"user", "assistant"} or not content:
                    continue
                connection.execute(
                    """
                    INSERT INTO messages (conversation_id, role, content, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        conversation["id"],
                        role,
                        content,
                        message.get("created_at") or _now(),
                    ),
                )
        return json_path

    def _ensure_workspace(self, project: dict) -> bool:
        folder = self.projects_root / project["name"]
        (folder / MATERIALS_DIR).mkdir(parents=True, exist_ok=True)
        (folder / RESULTS_DIR).mkdir(parents=True, exist_ok=True)
        relative = folder.relative_to(self.projects_root.parent).as_posix()
        changed = project.get("path") != relative
        project["path"] = relative
        return changed


def _clean_name(name: str) -> str:
    cleaned = " ".join(name.strip().split())
    if not cleaned:
        raise ProjectNameError("请填写项目名称。")
    if len(cleaned) > 40:
        raise ProjectNameError("项目名称请控制在 40 个字以内。")
    if any(char in cleaned for char in _INVALID_NAME):
        raise ProjectNameError('名称里不要包含 \\ / : * ? " < > |')
    if cleaned in {".", ".."} or cleaned.endswith("."):
        raise ProjectNameError("这个名称不能用作文件夹。")
    if cleaned.split(".", 1)[0].upper() in _RESERVED_NAMES:
        raise ProjectNameError("这个名称不能用作文件夹。")
    return cleaned


def _clean_filename(filename: str) -> str:
    name = Path(filename or "").name.strip()
    if not name or name in {".", ".."} or name.endswith((" ", ".")):
        raise MaterialError("这个文件名不能使用。")
    if any(char in name for char in _INVALID_NAME) or any(ord(char) < 32 for char in name):
        raise MaterialError("这个文件名不能使用。")
    if name.split(".", 1)[0].upper() in _RESERVED_NAMES:
        raise MaterialError("这个文件名不能使用。")
    if len(name) > 180:
        raise MaterialError("文件名太长。")
    return name


def _blank_project(name: str) -> dict:
    now = _now()
    return {
        "id": uuid.uuid4().hex[:12],
        "name": name,
        "created_at": now,
        "updated_at": now,
    }


def _blank(project_id: str) -> dict:
    now = _now()
    return {
        "id": uuid.uuid4().hex[:12],
        "project_id": project_id,
        "title": "新对话",
        "created_at": now,
        "updated_at": now,
        "messages": [],
    }


def _create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            path TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS conversations (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_conversations_project
            ON conversations(project_id, updated_at);
        CREATE INDEX IF NOT EXISTS idx_messages_conversation
            ON messages(conversation_id, id);
        """
    )


def _insert_project(connection: sqlite3.Connection, project: dict, ignore: bool = False) -> None:
    verb = "INSERT OR IGNORE" if ignore else "INSERT"
    connection.execute(
        f"""
        {verb} INTO projects (id, name, path, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            project["id"],
            project["name"],
            project.get("path") or "",
            project["created_at"],
            project["updated_at"],
        ),
    )


def _insert_conversation(
    connection: sqlite3.Connection,
    conversation: dict,
    ignore: bool = False,
) -> None:
    verb = "INSERT OR IGNORE" if ignore else "INSERT"
    connection.execute(
        f"""
        {verb} INTO conversations (id, project_id, title, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            conversation["id"],
            conversation["project_id"],
            conversation["title"],
            conversation["created_at"],
            conversation["updated_at"],
        ),
    )


def _project_from_row(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "path": row["path"] or "",
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _project_by_id(connection: sqlite3.Connection, project_id: str) -> dict | None:
    if not _ID.fullmatch(project_id or ""):
        return None
    row = connection.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    return None if row is None else _project_from_row(row)


def _project_named(connection: sqlite3.Connection, name: str) -> dict | None:
    row = connection.execute("SELECT * FROM projects WHERE name = ?", (name,)).fetchone()
    return None if row is None else _project_from_row(row)


def _conversation_from_row(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "project_id": row["project_id"],
        "title": row["title"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "messages": [],
    }


def _load_conversation(connection: sqlite3.Connection, conversation_id: str) -> dict | None:
    row = connection.execute(
        "SELECT * FROM conversations WHERE id = ?",
        (conversation_id,),
    ).fetchone()
    if row is None:
        return None
    conversation = _conversation_from_row(row)
    messages = connection.execute(
        """
        SELECT role, content, created_at FROM messages
        WHERE conversation_id = ?
        ORDER BY id
        """,
        (conversation_id,),
    ).fetchall()
    conversation["messages"] = [
        {"role": item["role"], "content": item["content"], "created_at": item["created_at"]}
        for item in messages
    ]
    return conversation


def _is_inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _project_summary(project: dict) -> dict:
    return {
        "id": project["id"],
        "name": project["name"],
        "path": project.get("path", ""),
        "folders": [MATERIALS_DIR, RESULTS_DIR],
        "created_at": project["created_at"],
        "updated_at": project["updated_at"],
    }


def _summary(conversation: dict, project_name: str = "") -> dict:
    item = {
        "id": conversation["id"],
        "project_id": conversation.get("project_id", ""),
        "title": conversation["title"],
        "created_at": conversation["created_at"],
        "updated_at": conversation["updated_at"],
    }
    if project_name:
        item["project_name"] = project_name
    return item


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
