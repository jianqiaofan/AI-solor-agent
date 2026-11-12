"""本机打开 AutoCAD 2020 的方式。

桌面快捷方式「AutoCAD 2020 - 简体中文 (Simplified Chinese).lnk」指向 acad.exe。
调用时先读快捷方式；快捷方式不在或读不出来时，用它当前指向的程序。
读快捷方式时不显示 PowerShell 窗口。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SHORTCUT = Path(r"C:\Users\Public\Desktop\AutoCAD 2020 - 简体中文 (Simplified Chinese).lnk")
INSTALLED_EXE = Path(r"D:\Program Files\Autodesk\AutoCAD 2020\acad.exe")
PROG_ID = "AutoCAD.Application.23.1"


def acad_executable() -> Path:
    target = _shortcut_target(SHORTCUT)
    if target is not None and target.is_file():
        return target
    if INSTALLED_EXE.is_file():
        return INSTALLED_EXE
    raise FileNotFoundError(
        "没有找到 AutoCAD 2020。请使用桌面快捷方式 AutoCAD 2020 所指的程序。"
    )


def metric_template(program: Path) -> Path | None:
    """毫米模板。找不到就让 AutoCAD 用自己的新建默认模板。"""
    cache = program.parent / "UserDataCache"
    candidates = [
        cache / "Template" / "acadiso.dwt",
        cache / "zh-cn" / "Template" / "acadiso.dwt",
        program.parent / "Template" / "acadiso.dwt",
    ]
    for path in candidates:
        if path.is_file():
            return path
    if cache.is_dir():
        found = sorted(cache.glob("*/Template/acadiso.dwt"))
        if found:
            return found[0]
    return None


def _shortcut_target(path: Path) -> Path | None:
    if not path.is_file():
        return None
    command = (
        "$sh = New-Object -ComObject WScript.Shell; "
        f"$lnk = $sh.CreateShortcut('{path}'); "
        "Write-Output $lnk.TargetPath"
    )
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    try:
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            check=False,
            capture_output=True,
            timeout=15,
            creationflags=flags,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    target = completed.stdout.decode("utf-8", errors="replace").strip()
    if not target:
        return None
    return Path(target)
