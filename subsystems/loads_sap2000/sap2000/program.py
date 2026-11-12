"""本机打开 SAP2000 26 的方式。

桌面快捷方式「SAP2000 26.lnk」指向安装目录里的 SAP2000.exe。
调用时先读快捷方式；快捷方式不在或读不出来时，用它当前指向的程序。
读快捷方式时不显示 PowerShell 窗口。启动后的 SAP2000 窗口保持打开。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SHORTCUT = Path(r"C:\Users\Public\Desktop\SAP2000 26.lnk")
INSTALLED_EXE = Path(r"E:\Program Files\Computers and Structures\SAP2000 26\SAP2000.exe")


def sap2000_executable() -> Path:
    target = _shortcut_target(SHORTCUT)
    if target is not None and target.is_file():
        return target
    if INSTALLED_EXE.is_file():
        return INSTALLED_EXE
    raise FileNotFoundError(
        "没有找到 SAP2000 26。请使用桌面快捷方式 SAP2000 26.lnk 所指的程序。"
    )


def start_sap2000(program: Path) -> subprocess.Popen[bytes]:
    """启动 SAP2000.exe，不等待它退出，窗口留在屏幕上。"""
    flags = 0
    if sys.platform == "win32":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    return subprocess.Popen(
        [str(program)],
        creationflags=flags,
    )


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
            text=True,
            timeout=15,
            creationflags=flags,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    target = completed.stdout.strip()
    if not target:
        return None
    return Path(target)
