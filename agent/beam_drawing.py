"""把主梁和立柱画成立面示意。"""

from __future__ import annotations

from agent.beam_layout import OVERHANG_MAX_MM, OVERHANG_MIN_MM, SPACING_MAX_MM, SPACING_MIN_MM, BeamLayout

_WIDTH = 960
_LEFT = 70
_RIGHT = 28


def render_svg(layout: BeamLayout) -> str:
    plot_width = _WIDTH - _LEFT - _RIGHT
    scale = plot_width / layout.length_mm if layout.length_mm > 0 else 1.0
    beam_y = 156
    ground_y = 300
    column_px = ground_y - beam_y
    true_px = layout.h_mm * scale
    stretch = column_px / true_px if true_px > 1 else 1.0
    height = 340

    def x_of(y_mm: float) -> float:
        return _LEFT + y_mm * scale

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {_WIDTH} {height}" '
        f'width="{_WIDTH}" height="{height}" role="img">',
        "<title>主梁与立柱布置</title>",
        f'<rect width="{_WIDTH}" height="{height}" fill="#ffffff"/>',
        _text(24, 28, "主梁与立柱", 16, "#1f2329", weight="600"),
        _text(
            24,
            50,
            f"布置 {layout.arrangement}    主梁长度 {_mm(layout.length_mm)} mm    "
            f"中心线高度 {_mm(layout.h_mm)} mm",
            13,
            "#667085",
        ),
    ]
    for left, right in layout.failed_spans:
        parts.append(
            f'<rect x="{x_of(left):.2f}" y="{beam_y - 8}" '
            f'width="{max(x_of(right) - x_of(left), 2):.2f}" height="{ground_y - beam_y + 16}" '
            f'fill="#fef3f2"/>'
        )
    parts.append(_ground(x_of(0) - 10, x_of(layout.length_mm) + 10, ground_y))
    parts.extend(_dimensions(layout, x_of, beam_y))
    parts.append(
        f'<line x1="{x_of(0):.2f}" y1="{beam_y}" x2="{x_of(layout.length_mm):.2f}" y2="{beam_y}" '
        f'stroke="#1f2329" stroke-width="5" stroke-linecap="round"/>'
    )
    for column in layout.columns:
        parts.extend(_column(column.kind, x_of(column.y_mm), beam_y, ground_y))
    parts.extend(_legend(24, ground_y + 28))
    note = "立面：Y 向右，Z 向上。"
    if stretch >= 1.5:
        note += f"高度约放大 {stretch:.0f} 倍，便于看清立柱。"
    parts.append(_text(24, ground_y + 52, note, 12, "#98a2b3"))
    parts.append("</svg>")
    return "".join(parts)


def _dimensions(layout: BeamLayout, x_of, beam_y: float) -> list[str]:
    marks = [0.0, *(column.y_mm for column in layout.columns), layout.length_mm]
    dim_y = beam_y - 46
    parts = [
        f'<line x1="{x_of(0):.2f}" y1="{dim_y}" x2="{x_of(layout.length_mm):.2f}" y2="{dim_y}" '
        f'stroke="#d0d5dd" stroke-width="1"/>'
    ]
    for y_mm in marks:
        parts.append(
            f'<line x1="{x_of(y_mm):.2f}" y1="{dim_y - 4}" x2="{x_of(y_mm):.2f}" y2="{beam_y - 10}" '
            f'stroke="#d0d5dd" stroke-width="1"/>'
        )
    for left, right in zip(marks, marks[1:]):
        gap = right - left
        if gap <= 0.001:
            continue
        edge = left == 0.0 or abs(right - layout.length_mm) <= 0.001
        width = x_of(right) - x_of(left)
        if not edge and width < 36:
            continue
        color = "#667085" if _gap_ok(gap, edge=edge) else "#b42318"
        if left == 0.0:
            anchor_x, anchor = x_of(0), "start"
        elif abs(right - layout.length_mm) <= 0.001:
            anchor_x, anchor = x_of(layout.length_mm), "end"
        else:
            anchor_x, anchor = x_of((left + right) / 2), "middle"
        parts.append(_text(anchor_x, dim_y - 8, _mm(gap), 12, color, anchor=anchor))
    return parts


def _gap_ok(gap: float, *, edge: bool) -> bool:
    if edge:
        return OVERHANG_MIN_MM - 0.05 <= gap <= OVERHANG_MAX_MM + 0.05
    return SPACING_MIN_MM - 0.05 <= gap <= SPACING_MAX_MM + 0.05


def _column(kind: str, x_pos: float, beam_y: float, ground_y: float) -> list[str]:
    if kind == "drive":
        color = "#c2410c"
        width = 3.5
        label = "驱动"
    else:
        color = "#0052d9"
        width = 2.5
        label = ""
    parts = [
        f'<line x1="{x_pos:.2f}" y1="{beam_y}" x2="{x_pos:.2f}" y2="{ground_y}" '
        f'stroke="{color}" stroke-width="{width}" stroke-linecap="round"/>',
        f'<rect x="{x_pos - 7:.2f}" y="{ground_y - 1}" width="14" height="5" fill="{color}"/>',
    ]
    if kind == "drive":
        parts.append(f'<circle cx="{x_pos:.2f}" cy="{beam_y}" r="5" fill="{color}"/>')
        parts.append(_text(x_pos, ground_y + 16, label, 11, color, anchor="middle"))
    return parts


def _ground(x1: float, x2: float, y_pos: float) -> str:
    hatch = []
    x_pos = x1
    while x_pos < x2:
        hatch.append(
            f'<line x1="{x_pos:.2f}" y1="{y_pos}" x2="{x_pos - 8:.2f}" y2="{y_pos + 8}" '
            f'stroke="#d0d5dd" stroke-width="1"/>'
        )
        x_pos += 14
    line = (
        f'<line x1="{x1:.2f}" y1="{y_pos}" x2="{x2:.2f}" y2="{y_pos}" '
        f'stroke="#98a2b3" stroke-width="1.5"/>'
    )
    return line + "".join(hatch)


def _legend(x_pos: float, y_pos: float) -> list[str]:
    return [
        f'<line x1="{x_pos}" y1="{y_pos}" x2="{x_pos + 22}" y2="{y_pos}" stroke="#1f2329" stroke-width="4"/>',
        _text(x_pos + 28, y_pos + 4, "主梁", 12, "#1f2329"),
        f'<line x1="{x_pos + 78}" y1="{y_pos - 7}" x2="{x_pos + 78}" y2="{y_pos + 7}" '
        f'stroke="#c2410c" stroke-width="3"/>',
        _text(x_pos + 88, y_pos + 4, "驱动立柱", 12, "#1f2329"),
        f'<line x1="{x_pos + 168}" y1="{y_pos - 7}" x2="{x_pos + 168}" y2="{y_pos + 7}" '
        f'stroke="#0052d9" stroke-width="3"/>',
        _text(x_pos + 178, y_pos + 4, "非驱动立柱", 12, "#1f2329"),
    ]


def _text(x_pos, y_pos, value, size, color, *, anchor="start", weight="400") -> str:
    return (
        f'<text x="{x_pos}" y="{y_pos}" fill="{color}" font-size="{size}" '
        f'font-weight="{weight}" font-family="Microsoft YaHei UI, Segoe UI, sans-serif" '
        f'text-anchor="{anchor}">{_escape(value)}</text>'
    )


def _escape(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _mm(value: float) -> str:
    if abs(value - round(value)) < 0.05:
        return str(int(round(value)))
    return f"{value:.1f}"
