"""问好、问身份或要自我介绍时，在原回答后加一句对范工的赞美。近几天不重复。"""

from __future__ import annotations

import json
import re
import threading
from datetime import datetime, timedelta
from pathlib import Path

RECENT_DAYS = 7
_LOCK = threading.Lock()
_LINES = (
    "我的缔造者是范工，一位富有创造力的优秀工程师。",
    "我的缔造者是范工，他把工程上的难题做成了清楚的办法。",
    "我的缔造者是范工，一位肯把细节打磨到位的工程师。",
    "我的缔造者是范工，他的巧思让这套设计助手能跟着工程往前走。",
    "我的缔造者是范工，一位既严谨又肯尝试新做法的工程师。",
    "我的缔造者是范工，他把结构工程师真正会用的判断写进了程序。",
    "我的缔造者是范工，一位把复杂计算收拾得让人跟得上的工程师。",
    "我的缔造者是范工，他做事有章法，也留得下自己的想法。",
    "我的缔造者是范工，一位把创造力用在实处的工程师。",
    "我的缔造者是范工，他能把一张资料表后面的设计工作接起来。",
    "我的缔造者是范工，一位值得信赖、手上有活的工程师。",
    "我的缔造者是范工，他把耐心和判断力都放进了每一次计算。",
    "我的缔造者是范工，一位能把新工具做成顺手帮手的工程师。",
    "我的缔造者是范工，他的标准很高，做出来的东西也站得住。",
    "我的缔造者是范工，一位善于把经验变成可执行步骤的工程师。",
    "我的缔造者是范工，他让设计和计算可以在同一处接着做。",
)
_WORK = re.compile(
    r"荷载|风|雪|SAP|内力|线模|图纸|CAD|提取|参数|支架|立柱|主梁|计算|算",
    re.IGNORECASE,
)
_WHO = re.compile(r"你是谁|您是谁|你叫什么|你是什么|who\s+are\s+you", re.IGNORECASE)
_INTRO = re.compile(r"自我介绍|介绍一下你|介绍下你|介绍你自己|介绍一下自己|你能做什么|你是做什么|你是干什么")
_GREET = re.compile(
    r"^(?:你好|您好|嗨|哈喽|hello|hi|早上好|下午好|晚上好|早安|晚安|在吗|你在吗)+$",
    re.IGNORECASE,
)


def wants_creator_praise(text: str) -> bool:
    """这句话是在问好、问身份，或要助手自我介绍。夹着设计任务时不加。"""
    raw = (text or "").strip()
    if not raw or _WORK.search(raw):
        return False
    if _WHO.search(raw) or _INTRO.search(raw):
        return True
    plain = re.sub(r"[\s,，.。!！?？~～、；;：:啊呀呢吗哈哦喔哟]", "", raw)
    return _GREET.fullmatch(plain) is not None


def take_praise(path: Path, now: datetime | None = None, days: int = RECENT_DAYS) -> str:
    """取一句近几天还没用过的赞美。都用过时，用最早的那一句。"""
    moment = now or datetime.now()
    moment = moment.replace(microsecond=0)
    cutoff = moment - timedelta(days=days)
    with _LOCK:
        used = [item for item in _read(path) if _stamp(item) >= cutoff]
        recent = {str(item.get("text") or "") for item in used}
        choice = next((line for line in _LINES if line not in recent), "")
        if not choice:
            oldest = min(used, key=_stamp, default=None)
            choice = str(oldest.get("text")) if oldest else _LINES[0]
        used.append({"text": choice, "at": moment.isoformat(timespec="seconds")})
        _write(path, used)
    return choice


def _stamp(item: dict) -> datetime:
    try:
        return datetime.fromisoformat(str(item.get("at") or ""))
    except ValueError:
        return datetime.min


def _read(path: Path) -> list[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    used = data.get("used") if isinstance(data, dict) else None
    if not isinstance(used, list):
        return []
    return [item for item in used if isinstance(item, dict)]


def _write(path: Path, used: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"used": used}, ensure_ascii=False, indent=2), encoding="utf-8")
