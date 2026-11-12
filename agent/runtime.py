"""打开设计助手窗口，并在本机启动页面服务。"""

from __future__ import annotations

import logging
import os
import socket
import sys
import threading
import time
import webbrowser

from agent.settings import DATA_DIR, PORT, reload_env


def main() -> int:
    _configure_stdio()
    _configure_logging()
    reload_env()
    if _port_busy():
        _alert(f"端口 {PORT} 已被占用。请关掉上一个设计助手窗口后再打开。")
        return 1
    if _server_only():
        print(f"设计助手： http://127.0.0.1:{PORT}")
        try:
            _serve()
        except KeyboardInterrupt:
            return 0
        return 0

    thread = threading.Thread(target=_serve, name="agent-server", daemon=True)
    thread.start()
    if not _wait_until_up():
        _alert(f"页面没有打开。端口 {PORT} 可能被占用，或依赖还没有装好。")
        return 1
    _open_window()
    return 0


def _server_only() -> bool:
    import os

    return os.environ.get("AGENT_SERVER_ONLY") == "1"


def _serve() -> None:
    import uvicorn

    from agent.server import app

    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="info", access_log=False)


def _open_window() -> None:
    url = f"http://127.0.0.1:{PORT}"
    width, height = 1360, 860
    origin_x, origin_y = _initial_origin(width, height)
    try:
        import webview

        window = None
        for options in (
            {
                "width": width,
                "height": height,
                "min_size": (1024, 680),
                "background_color": "#FFFFFF",
                "text_select": True,
            },
            {"width": width, "height": height, "min_size": (1024, 680)},
        ):
            try:
                window = webview.create_window(
                    "设计助手", url, x=origin_x, y=origin_y, **options
                )
                break
            except TypeError:
                continue
        if window is None:
            raise RuntimeError("无法创建窗口")

        def _on_shown() -> None:
            try:
                if window.x < -8000 or window.y < -8000:
                    window.restore()
                    window.move(origin_x, origin_y)
            except Exception:
                logging.getLogger("agent").exception("窗口位置没有纠正")

        window.events.shown += _on_shown
        webview.start()
        return
    except Exception:
        logging.getLogger("agent").exception("独立窗口没有打开，改用浏览器")
    webbrowser.open(url)
    _hold_until_closed()


def _wait_until_up() -> bool:
    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", PORT), timeout=0.2):
                return True
        except OSError:
            time.sleep(0.1)
    return False


def _port_busy() -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex(("127.0.0.1", PORT)) == 0


def _hold_until_closed() -> None:
    import tkinter as tk

    root = tk.Tk()
    root.title("设计助手")
    width, height = 380, 150
    origin_x, origin_y = _initial_origin(width, height)
    root.geometry(f"{width}x{height}+{origin_x}+{origin_y}")
    tk.Label(
        root,
        text="设计助手已在浏览器中打开。\n关闭这个小窗口就会退出。",
        justify="center",
    ).pack(expand=True, padx=16, pady=16)
    root.mainloop()


def _configure_stdio() -> None:
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")


def _configure_logging() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    handlers: list[logging.Handler] = [
        logging.FileHandler(DATA_DIR / "server.log", encoding="utf-8")
    ]
    if sys.stderr is not None:
        handlers.append(logging.StreamHandler())
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=handlers,
    )


def centered_origin(
    screen_x: int,
    screen_y: int,
    screen_width: int,
    screen_height: int,
    width: int,
    height: int,
) -> tuple[int, int]:
    """把窗口放在一块屏幕区域的正中。区域比窗口小时贴住左上角。"""
    return (
        screen_x + max(0, (screen_width - width) // 2),
        screen_y + max(0, (screen_height - height) // 2),
    )


def _initial_origin(width: int, height: int) -> tuple[int, int]:
    try:
        return centered_origin(*_screen_work_area(), width, height)
    except Exception:
        logging.getLogger("agent").exception("没有读到屏幕尺寸，窗口改放在左上角")
        return 80, 60


def _screen_work_area() -> tuple[int, int, int, int]:
    if sys.platform == "win32":
        area = _windows_work_area()
        if area is not None:
            return area
    return _tk_screen_size()


def _windows_work_area() -> tuple[int, int, int, int] | None:
    import ctypes
    from ctypes import wintypes

    class RECT(ctypes.Structure):
        _fields_ = (
            ("left", wintypes.LONG),
            ("top", wintypes.LONG),
            ("right", wintypes.LONG),
            ("bottom", wintypes.LONG),
        )

    rect = RECT()
    # SPI_GETWORKAREA：主屏幕去掉任务栏后的区域，坐标和 pywebview 的逻辑像素一致。
    if not ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0):
        return None
    width = rect.right - rect.left
    height = rect.bottom - rect.top
    if width <= 0 or height <= 0:
        return None
    return rect.left, rect.top, width, height


def _tk_screen_size() -> tuple[int, int, int, int]:
    import tkinter as tk

    root = tk.Tk()
    root.withdraw()
    try:
        return 0, 0, int(root.winfo_screenwidth()), int(root.winfo_screenheight())
    finally:
        root.destroy()


def _alert(text: str) -> None:
    logging.getLogger("agent").error(text)
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("设计助手", text)
        root.destroy()
    except Exception:
        print(text, file=sys.stderr)
