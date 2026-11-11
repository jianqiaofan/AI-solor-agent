"""读取项目根目录的 .env。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = Path(__file__).resolve().parent
ENV_PATH = ROOT / ".env"
DATA_DIR = PACKAGE / "data"
STATIC_DIR = PACKAGE / "static"
PORT = 8765

_ENV_KEYS = (
    "DEEPSEEK_API_KEY",
    "DEEPSEEK_BASE_URL",
    "DEEPSEEK_API_BASE",
    "DEEPSEEK_MODEL",
)


@dataclass(frozen=True)
class Settings:
    api_key: str
    base_url: str
    model: str


class ConfigError(Exception):
    """配置还不能用来调用模型。"""


def reload_env(path: Path | None = None) -> None:
    load_dotenv(path or ENV_PATH, override=True)
    for name in _ENV_KEYS:
        value = os.environ.get(name)
        if value is None:
            continue
        os.environ[name] = value.strip().strip('"').strip("'")


def require_settings() -> Settings:
    key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not key:
        raise ConfigError(
            "还没有 API Key。请在项目根目录的 .env 里填写 DEEPSEEK_API_KEY，保存后刷新此页。"
        )
    model = os.environ.get("DEEPSEEK_MODEL", "").strip() or "deepseek-flash"
    base = (
        os.environ.get("DEEPSEEK_BASE_URL", "").strip()
        or os.environ.get("DEEPSEEK_API_BASE", "").strip()
        or "https://api.deepseek.com"
    )
    return Settings(api_key=key, base_url=base.rstrip("/"), model=model)
