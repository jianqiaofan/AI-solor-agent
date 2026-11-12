"""把线模中心线转成 AutoCAD 立面：主梁、立柱，以及间距、总长和高度。

线模坐标是 (X, Y, Z)，Y 沿主梁，Z 为高度，单位 mm。
立面画在 CAD 的 XY 平面：CAD 的 X 取线模的 Y，CAD 的 Y 取线模的 Z。
"""

from __future__ import annotations

from typing import Any

CHAIN_OFFSET_MM = 2000.0
OVERALL_OFFSET_MM = 4500.0
HEIGHT_OFFSET_MM = 2500.0

LAYERS = (
    ("主梁", 2),
    ("立柱", 4),
    ("驱动立柱", 1),
    ("标注", 3),
)
_BEAM = "主梁"
_COLUMN = "立柱"
_DRIVE = "驱动立柱"
_DIM = "标注"


def plan(model: dict[str, Any]) -> dict[str, Any]:
    """返回要画的图层、直线和尺寸。坐标都是 CAD 立面里的毫米。"""
    if not isinstance(model, dict) or model.get("kind") != "line_model":
        raise ValueError("线模文件读不出来。")
    if model.get("units") != "mm":
        raise ValueError("线模单位不是 mm。")
    if model.get("issues"):
        raise ValueError("线模还有未解决的问题，不能出图。")
    beam = model.get("beam")
    if not isinstance(beam, dict):
        raise ValueError("线模没有主梁。")
    start = _xyz(beam.get("start"), "主梁起点")
    end = _xyz(beam.get("end"), "主梁终点")
    columns = model.get("columns")
    if not isinstance(columns, list) or not columns:
        raise ValueError("线模没有立柱，不能出图。")

    beam_start = _to_cad(start)
    beam_end = _to_cad(end)
    level = beam_start[1]
    lines = [
        {"layer": _BEAM, "start": beam_start, "end": beam_end},
    ]
    stations = [beam_start[0], beam_end[0]]
    ordered = sorted(columns, key=lambda item: float(item["y_mm"]))
    drawn: list[dict[str, Any]] = []
    for index, column in enumerate(ordered, start=1):
        bottom = _to_cad(_xyz(column.get("bottom"), f"立柱 {index} 下端"))
        top = _to_cad(_xyz(column.get("top"), f"立柱 {index} 上端"))
        layer = _DRIVE if column.get("kind") == "drive" else _COLUMN
        lines.append({"layer": layer, "start": bottom, "end": top})
        stations.append(float(column["y_mm"]))
        drawn.append({"bottom": bottom, "top": top})

    marks = _stations(stations)
    if len(marks) < 2:
        raise ValueError("线模的主梁长度不够，不能标注。")
    dimensions = _chain(marks, level)
    dimensions.append(
        {
            "layer": _DIM,
            "start": (marks[0], level, 0.0),
            "end": (marks[-1], level, 0.0),
            "at": ((marks[0] + marks[-1]) / 2.0, level + OVERALL_OFFSET_MM, 0.0),
        }
    )
    first = drawn[0]
    height_x = first["bottom"][0] - HEIGHT_OFFSET_MM
    dimensions.append(
        {
            "layer": _DIM,
            "start": first["bottom"],
            "end": first["top"],
            "at": (height_x, (first["bottom"][1] + first["top"][1]) / 2.0, 0.0),
        }
    )
    measures = [right - left for left, right in zip(marks, marks[1:])]
    measures.append(marks[-1] - marks[0])
    measures.append(abs(first["top"][1] - first["bottom"][1]))
    return {
        "decimals": _decimals(measures),
        "layers": [{"name": name, "color": color} for name, color in LAYERS],
        "lines": lines,
        "dimensions": dimensions,
    }


def _chain(marks: list[float], level: float) -> list[dict[str, Any]]:
    dims = []
    for left, right in zip(marks, marks[1:]):
        if right - left <= 0.05:
            continue
        dims.append(
            {
                "layer": _DIM,
                "start": (left, level, 0.0),
                "end": (right, level, 0.0),
                "at": ((left + right) / 2.0, level + CHAIN_OFFSET_MM, 0.0),
            }
        )
    return dims


def _stations(values: list[float]) -> list[float]:
    kept: list[float] = []
    for value in sorted(values):
        if kept and abs(value - kept[-1]) <= 0.05:
            continue
        kept.append(value)
    return kept


def _decimals(measures: list[float]) -> int:
    if all(abs(value - round(value)) < 0.05 for value in measures):
        return 0
    return 1


def _to_cad(point: tuple[float, float, float]) -> tuple[float, float, float]:
    return (point[1], point[2], 0.0)


def _xyz(value: Any, label: str) -> tuple[float, float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError(f"线模的{label}不是坐标。")
    try:
        return (float(value[0]), float(value[1]), float(value[2]))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"线模的{label}不是坐标。") from exc
