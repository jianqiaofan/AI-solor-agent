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
    try:
        import webview

        window = None
        for options in (
            {
                "width": 1360,
                "height": 860,
                "min_size": (1024, 680),
                "background_color": "#FFFFFF",
                "text_select": True,
            },
            {"width": 1360, "height": 860, "min_size": (1024, 680)},
        ):
            try:
                window = webview.create_window("设计助手", url, x=80, y=60, **options)
                break
            except TypeError:
                continue
        if window is None:
            raise RuntimeError("无法创建窗口")

        def _on_shown() -> None:
            try:
                if window.x < -8000 or window.y < -8000:
                    window.restore()
                    window.move(80, 60)
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
    root.geometry("380x150")
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
