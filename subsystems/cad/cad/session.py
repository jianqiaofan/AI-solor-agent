"""打开 AutoCAD 2020，在新图里画立面并保存。

已经开着 AutoCAD 2020 时就在里面新建一张图，不关掉用户正在看的其他图。
窗口留在屏幕上。
"""

from __future__ import annotations

import array
import time
from pathlib import Path
from typing import Any

from cad.drawing import plan
from cad.program import PROG_ID, acad_executable, metric_template

_PROG_IDS = (PROG_ID, "AutoCAD.Application.23")
_REJECTED = -2147418111
_MILLIMETERS = 4
_DECIMAL = 2


def draw_line_model(model: dict[str, Any], destination: Path) -> Path:
    """画出立面并保存。返回实际打开的 acad.exe。"""
    view = plan(model)
    program = acad_executable()
    app = _connect()
    _render(app, program, view, Path(destination))
    return program


def _running() -> Any:
    import comtypes
    from comtypes import client

    for progid in _PROG_IDS:
        try:
            return client.GetActiveObject(progid, dynamic=True)
        except (OSError, comtypes.COMError):
            continue
    return None


def _start() -> Any:
    import comtypes
    from comtypes import client

    last: Exception | None = None
    for progid in _PROG_IDS:
        try:
            return client.CreateObject(progid, dynamic=True)
        except (OSError, comtypes.COMError) as exc:
            last = exc
    raise RuntimeError("AutoCAD 2020 没有打开。") from last


def _connect() -> Any:
    import comtypes

    app = _running()
    if app is None:
        app = _start()
    try:
        _wait_ready(app)
    except comtypes.COMError as exc:
        raise RuntimeError("AutoCAD 没有响应。如果屏幕上有对话框，先关掉再试。") from exc
    app.Visible = True
    try:
        app.WindowState = 3
    except comtypes.COMError:
        pass
    return app


def _wait_ready(app: Any) -> None:
    import comtypes

    last: Exception | None = None
    for _ in range(40):
        try:
            app.Visible = True
            _ = app.Documents
            return
        except comtypes.COMError as exc:
            last = exc
            if getattr(exc, "hresult", None) != _REJECTED:
                raise
            time.sleep(0.5)
    if last is not None:
        raise last


def _call(action, tries: int = 40):
    """AutoCAD 刚启动或正在弹窗时会拒绝调用，隔一会儿再试。"""
    last: Exception | None = None
    for _ in range(tries):
        try:
            return action()
        except Exception as exc:
            if not _rejected(exc):
                raise
            last = exc
            time.sleep(0.4)
    if last is not None:
        raise last
    return None


def _rejected(exc: Exception) -> bool:
    if getattr(exc, "hresult", None) == _REJECTED:
        return True
    args = getattr(exc, "args", ())
    return bool(args) and args[0] == _REJECTED


def _render(app: Any, program: Path, view: dict[str, Any], destination: Path) -> None:
    template = metric_template(program)
    if template is None:
        _call(lambda: app.Documents.Add())
    else:
        _call(lambda: app.Documents.Add(str(template)))
    # Add 的返回值不一定是带绘图方法的文档，改用当前图。
    document = _call(lambda: app.ActiveDocument)
    _call(lambda: document.Activate())

    def _var(name: str, value: int) -> None:
        _call(lambda: document.SetVariable(name, value))

    _var("INSUNITS", _MILLIMETERS)
    _var("LUNITS", _DECIMAL)
    _var("LUPREC", int(view["decimals"]))
    _var("DIMDEC", int(view["decimals"]))
    _var("DIMTXT", 350)
    _var("DIMASZ", 250)
    _var("DIMEXO", 100)
    _var("DIMEXE", 150)
    _var("DIMGAP", 80)
    _var("DIMTIH", 0)
    _var("DIMTOH", 0)
    _var("DIMTAD", 1)
    _var("ISAVEBAK", 0)
    for layer in view["layers"]:
        _ensure_layer(document, str(layer["name"]), int(layer["color"]))
    space = _call(lambda: document.ModelSpace)
    for line in view["lines"]:
        entity = _call(lambda line=line: space.AddLine(_point(*line["start"]), _point(*line["end"])))
        _call(lambda entity=entity, line=line: setattr(entity, "Layer", line["layer"]))
    for dim in view["dimensions"]:
        entity = _call(
            lambda dim=dim: space.AddDimAligned(
                _point(*dim["start"]),
                _point(*dim["end"]),
                _point(*dim["at"]),
            )
        )
        _call(lambda entity=entity, dim=dim: setattr(entity, "Layer", dim["layer"]))
    _close_same_path(app, document, destination)
    _save(document, destination)
    try:
        _call(lambda: app.ZoomExtents())
    except Exception:
        pass
    app.Visible = True


def _ensure_layer(document: Any, name: str, color: int) -> None:
    layers = _call(lambda: document.Layers)
    try:
        layer = _call(lambda: layers.Item(name))
    except Exception:
        layer = _call(lambda: layers.Add(name))
    _call(lambda: setattr(layer, "Color", color))


def _close_same_path(app: Any, current: Any, destination: Path) -> None:
    """同一路径的旧图还开着时先关掉，否则这一张存不进去。"""
    target = str(destination.resolve()).lower()
    documents = app.Documents
    index = int(documents.Count)
    while index > 0:
        index -= 1
        try:
            other = documents.Item(index)
        except Exception:
            continue
        if other == current:
            continue
        try:
            full = str(other.FullName or "")
        except Exception:
            continue
        if not full:
            continue
        try:
            same = str(Path(full).resolve()).lower() == target
        except OSError:
            same = full.lower() == target
        if same:
            other.Close(False)


def _save(document: Any, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    previous = _call(lambda: document.GetVariable("FILEDIA"))
    _call(lambda: document.SetVariable("FILEDIA", 0))
    try:
        _call(lambda: document.SaveAs(str(destination.resolve())))
    finally:
        try:
            _call(lambda: document.SetVariable("FILEDIA", previous))
        except Exception:
            pass


def _point(x: float, y: float, z: float) -> array.array[float]:
    return array.array("d", (float(x), float(y), float(z)))
