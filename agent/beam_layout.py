"""按主梁立柱布置规则计算中心线和立柱坐标。"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass

MODULE_GAP_MM = 20.0
DRIVE_GAP_MM = 500.0
SPACING_MIN_MM = 7200.0
SPACING_MAX_MM = 9000.0
OVERHANG_MIN_MM = 900.0
OVERHANG_MAX_MM = 1500.0
OVERHANG_AIM_MM = 1200.0
ROUND_MM = 100.0
_TOL = 1e-6


@dataclass(frozen=True)
class Column:
    kind: str
    y_mm: float
    drive_index: int | None = None


@dataclass(frozen=True)
class BeamLayout:
    h_mm: float
    length_mm: float
    arrangement: str
    counts: tuple[int, ...]
    columns: tuple[Column, ...]
    issues: tuple[str, ...]
    failed_spans: tuple[tuple[float, float], ...]

    @property
    def overhang_start_mm(self) -> float | None:
        if not self.columns:
            return None
        return self.columns[0].y_mm

    @property
    def overhang_end_mm(self) -> float | None:
        if not self.columns:
            return None
        return self.length_mm - self.columns[-1].y_mm


def layout_view(geometry: dict) -> dict:
    """给页面用的布置结果。缺参数时不画图。"""
    missing = _missing_inputs(geometry)
    if missing:
        return {"ready": False, "message": "还缺" + "、".join(missing) + "，暂时不能画主梁和立柱。"}
    try:
        length = float(geometry["module_length_mm"])
        width = float(geometry["module_width_mm"])
        clearance = float(geometry["ground_clearance_mm"])
    except (TypeError, ValueError):
        return {"ready": False, "message": "组件长度、宽度或离地高度不是数字。"}
    if length <= 0 or width <= 0 or clearance < 0:
        return {"ready": False, "message": "组件长度和宽度要大于 0，离地高度不能为负。"}
    counts = parse_counts(str(geometry["arrangement_columns"]))
    if counts is None:
        return {
            "ready": False,
            "message": "布置列数要写成正整数，段与段之间用 / 分开，例如 22/22。",
        }
    layout = arrange(length, width, clearance, counts, str(geometry["arrangement_columns"]).strip())
    columns = []
    previous = None
    for index, column in enumerate(layout.columns, start=1):
        gap = None if previous is None else column.y_mm - previous
        columns.append(
            {
                "index": index,
                "kind": column.kind,
                "y_mm": column.y_mm,
                "gap_mm": gap,
                "drive_index": column.drive_index,
            }
        )
        previous = column.y_mm
    from agent.beam_drawing import render_svg

    return {
        "ready": True,
        "arrangement": layout.arrangement,
        "h_mm": layout.h_mm,
        "length_mm": layout.length_mm,
        "overhang_start_mm": layout.overhang_start_mm,
        "overhang_end_mm": layout.overhang_end_mm,
        "issues": list(layout.issues),
        "columns": columns,
        "svg": render_svg(layout),
    }


def arrange(
    module_length_mm: float,
    module_width_mm: float,
    ground_clearance_mm: float,
    counts: list[int] | tuple[int, ...],
    arrangement: str,
) -> BeamLayout:
    pitch = module_width_mm + MODULE_GAP_MM
    length = sum(count * pitch for count in counts) + (len(counts) - 1) * DRIVE_GAP_MM
    drives = _drive_positions(counts, pitch)
    height = 0.5 * module_length_mm * math.cos(math.radians(60)) + ground_clearance_mm
    zones = _zones(length, drives)
    issues: list[str] = []
    failed: list[tuple[float, float]] = []
    solvable = []
    for zone in zones:
        options = _options(zone)
        if options:
            solvable.append((zone, options))
        else:
            issues.append(_unsolvable(zone))
            failed.append((zone.left, zone.right))
    chosen = _best_choice(length, drives, solvable)
    columns = _columns(length, drives, chosen)
    return BeamLayout(
        h_mm=height,
        length_mm=length,
        arrangement=arrangement,
        counts=tuple(counts),
        columns=tuple(columns),
        issues=tuple(issues),
        failed_spans=tuple(failed),
    )


def parse_counts(arrangement: str) -> list[int] | None:
    parts = [part.strip() for part in arrangement.split("/")]
    if not parts or any(not part.isdigit() or int(part) <= 0 for part in parts):
        return None
    return [int(part) for part in parts]


@dataclass(frozen=True)
class _Zone:
    kind: str
    left: float
    right: float

    @property
    def span(self) -> float:
        return self.right - self.left


@dataclass(frozen=True)
class _Option:
    s: int
    d: float | None = None
    lo: float | None = None
    hi: float | None = None


def _drive_positions(counts: list[int] | tuple[int, ...], pitch: float) -> list[float]:
    positions = []
    for index in range(1, len(counts)):
        covered = sum(counts[:index]) * pitch + (index - 1) * DRIVE_GAP_MM + DRIVE_GAP_MM / 2
        positions.append(covered)
    return positions


def _zones(length: float, drives: list[float]) -> list[_Zone]:
    if not drives:
        return [_Zone("whole", 0.0, length)]
    zones = [_Zone("start", 0.0, drives[0])]
    zones.extend(_Zone("interior", left, right) for left, right in zip(drives, drives[1:]))
    zones.append(_Zone("end", drives[-1], length))
    return zones


def _options(zone: _Zone) -> list[_Option]:
    if zone.kind == "interior":
        return _interior_options(zone.span)
    if zone.kind == "whole":
        return _whole_options(zone.span)
    return _end_options(zone.span)


def _interior_options(span: float) -> list[_Option]:
    options = []
    for bays in range(1, _floor((span - _TOL) / SPACING_MIN_MM) + 1):
        spacing = span / bays
        if SPACING_MIN_MM - _TOL <= spacing <= SPACING_MAX_MM + _TOL:
            options.append(_Option(bays, d=spacing))
    return options


def _end_options(span: float) -> list[_Option]:
    options = []
    if OVERHANG_MIN_MM - _TOL <= span <= OVERHANG_MAX_MM + _TOL:
        options.append(_Option(0))
    for bays in range(1, _floor((span - OVERHANG_MIN_MM) / SPACING_MIN_MM) + 1):
        lo = max(SPACING_MIN_MM, (span - OVERHANG_MAX_MM) / bays)
        hi = min(SPACING_MAX_MM, (span - OVERHANG_MIN_MM) / bays)
        if lo <= hi + _TOL:
            options.append(_Option(bays, lo=lo, hi=hi))
    return options


def _whole_options(length: float) -> list[_Option]:
    options = []
    upper = _floor((length - 2 * OVERHANG_MIN_MM) / SPACING_MIN_MM)
    for bays in range(1, upper + 1):
        lo = max(SPACING_MIN_MM, (length - 2 * OVERHANG_MAX_MM) / bays)
        hi = min(SPACING_MAX_MM, (length - 2 * OVERHANG_MIN_MM) / bays)
        if lo <= hi + _TOL:
            options.append(_Option(bays, lo=lo, hi=hi))
    if not options and 2 * OVERHANG_MIN_MM - _TOL <= length <= 2 * OVERHANG_MAX_MM + _TOL:
        options.append(_Option(0))
    return options


def _best_choice(
    length: float,
    drives: list[float],
    solvable: list[tuple[_Zone, list[_Option]]],
) -> list[tuple[_Zone, _Option, float | None]]:
    if not solvable:
        return []
    best_key = None
    best: list[tuple[_Zone, _Option, float | None]] = []
    pools = [options for _zone, options in solvable]
    for combo in itertools.product(*pools):
        assigned = _assign_spacings(length, solvable, combo)
        if assigned is None:
            continue
        key = _score(length, drives, assigned)
        if best_key is None or key < best_key:
            best_key = key
            best = assigned
    return best


def _assign_spacings(length, solvable, combo):
    fixed = [(zone, option) for (zone, _options), option in zip(solvable, combo) if option.d is not None]
    free = [(zone, option) for (zone, _options), option in zip(solvable, combo) if option.lo is not None]
    idle = [(zone, option) for (zone, _options), option in zip(solvable, combo) if option.s == 0]
    fixed_values = [option.d for _zone, option in fixed]
    if len(free) > 2:
        return None
    chosen: dict[int, float] = {}
    if len(free) == 1:
        chosen[id(free[0][1])] = _choose_one(length, free[0][0], free[0][1], fixed_values)
    elif len(free) == 2:
        pair = _choose_two(length, free[0], free[1], fixed)
        if pair is None:
            return None
        chosen[id(free[0][1])] = pair[0]
        chosen[id(free[1][1])] = pair[1]
    assigned = []
    for (zone, _options), option in zip(solvable, combo):
        if option.d is not None:
            assigned.append((zone, option, option.d))
        elif option.s == 0:
            assigned.append((zone, option, None))
        else:
            assigned.append((zone, option, chosen[id(option)]))
    if len(assigned) != len(fixed) + len(free) + len(idle):
        return None
    return assigned


def _choose_one(length: float, zone: _Zone, option: _Option, fixed: list[float]) -> float:
    lo, hi = _tight(option.lo, option.hi, fixed)
    return _pick(length, [(zone, option)], lo, hi)


def _choose_two(length, first, second, fixed: list[tuple[_Zone, _Option]]):
    zone_a, option_a = first
    zone_b, option_b = second
    fixed_values = [option.d for _zone, option in fixed if option.d is not None]
    pool_a = _pool(length, zone_a, option_a, fixed_values, zone_b, option_b)
    pool_b = _pool(length, zone_b, option_b, fixed_values, zone_a, option_a)
    shared = _shared_spacing(length, zone_a, option_a, zone_b, option_b, fixed_values)
    if shared is not None:
        pool_a.append(shared)
        pool_b.append(shared)
    best = None
    best_pair = None
    fixed_rows = [(zone, option, option.d) for zone, option in fixed]
    for left in pool_a:
        for right in pool_b:
            key = _spacing_key(
                length,
                [(zone_a, option_a, left), (zone_b, option_b, right), *fixed_rows],
            )
            if best is None or key < best:
                best = key
                best_pair = (left, right)
    return best_pair


def _tight(lo: float, hi: float, fixed: list[float]) -> tuple[float, float]:
    if not fixed:
        return lo, hi
    low = min(fixed)
    high = max(fixed)
    if hi < low - _TOL:
        return hi, hi
    if lo > high + _TOL:
        return lo, lo
    return max(lo, low), min(hi, high)


def _pick(length: float, zones: list[tuple[_Zone, _Option]], lo: float, hi: float) -> float:
    multiples = _multiples(lo, hi)
    pool = multiples or [_overhang_spacing(length, zones, lo, hi)]
    return min(pool, key=lambda spacing: _overhang_key(length, zones, spacing))


def _pool(length, zone, option, fixed, other_zone, other_option) -> list[float]:
    lo, hi = option.lo, option.hi
    values = [lo, hi]
    ideal = _ideal_spacing(length, zone, option)
    if lo - _TOL <= ideal <= hi + _TOL:
        values.append(ideal)
    for value in fixed:
        if lo - _TOL <= value <= hi + _TOL:
            values.append(value)
    for extra in (
        other_option.lo,
        other_option.hi,
        _ideal_spacing(length, other_zone, other_option),
    ):
        if extra is not None and lo - _TOL <= extra <= hi + _TOL:
            values.append(extra)
    values.extend(_multiples(lo, hi))
    return values


def _shared_spacing(length, zone_a, option_a, zone_b, option_b, fixed: list[float]):
    lo = max(option_a.lo, option_b.lo)
    hi = min(option_a.hi, option_b.hi)
    if fixed:
        lo = max(lo, min(fixed))
        hi = min(hi, max(fixed))
    if lo > hi + _TOL:
        return None
    return _pick(length, [(zone_a, option_a), (zone_b, option_b)], lo, hi)


def _ideal_spacing(length: float, zone: _Zone, option: _Option) -> float:
    if zone.kind == "whole":
        return (length - 2 * OVERHANG_AIM_MM) / option.s
    return (zone.span - OVERHANG_AIM_MM) / option.s


def _overhang_spacing(length, zones: list[tuple[_Zone, _Option]], lo: float, hi: float) -> float:
    if len(zones) == 1:
        return _clamp(_ideal_spacing(length, zones[0][0], zones[0][1]), lo, hi)
    (zone_a, option_a), (zone_b, option_b) = zones
    aim_a = _ideal_spacing(length, zone_a, option_a)
    aim_b = _ideal_spacing(length, zone_b, option_b)
    if option_a.s == option_b.s:
        low, high = sorted((aim_a, aim_b))
        segment_lo = max(lo, low)
        segment_hi = min(hi, high)
        if segment_lo <= segment_hi + _TOL:
            return _clamp(segment_hi, lo, hi)
    heavier = aim_a if option_a.s > option_b.s else aim_b
    return _clamp(heavier, lo, hi)


def _overhang_key(length: float, zones: list[tuple[_Zone, _Option]], spacing: float):
    start = end = None
    for zone, option in zones:
        overhang = _zone_overhang(length, zone, option, spacing)
        if zone.kind in ("start", "whole"):
            start = overhang
        if zone.kind in ("end", "whole"):
            end = overhang
    if start is None:
        start = OVERHANG_AIM_MM
    if end is None:
        end = OVERHANG_AIM_MM
    return (abs(start - OVERHANG_AIM_MM) + abs(end - OVERHANG_AIM_MM), start, spacing)


def _zone_overhang(length: float, zone: _Zone, option: _Option, spacing: float | None) -> float:
    if zone.kind == "whole":
        if option.s == 0 or spacing is None:
            return length / 2
        return (length - option.s * spacing) / 2
    if option.s == 0 or spacing is None:
        return zone.span
    return zone.span - option.s * spacing


def _spacing_key(length, assigned):
    bays: list[float] = []
    start = end = None
    for zone, option, spacing in assigned:
        if option.s > 0 and spacing is not None:
            bays.extend([spacing] * option.s)
        overhang = _zone_overhang(length, zone, option, spacing)
        if zone.kind in ("start", "whole"):
            start = overhang
        if zone.kind in ("end", "whole"):
            end = overhang
    spread = 0.0 if not bays else max(bays) - min(bays)
    multiples = sum(1 for bay in bays if _divisible(bay))
    if start is None:
        start = OVERHANG_AIM_MM
    if end is None:
        end = OVERHANG_AIM_MM
    return (
        round(spread, 6),
        -multiples,
        round(abs(start - OVERHANG_AIM_MM) + abs(end - OVERHANG_AIM_MM), 6),
        round(start, 6),
        tuple(round(bay, 6) for bay in bays),
    )


def _score(length, drives, assigned):
    del drives
    return _spacing_key(length, assigned)


def _columns(length, drives, assigned) -> list[Column]:
    found: dict[float, Column] = {}
    for index, y_mm in enumerate(drives, start=1):
        _put(found, Column("drive", y_mm, index))
    for zone, option, spacing in assigned:
        for y_mm in _plain_positions(length, zone, option, spacing):
            _put(found, Column("plain", y_mm))
    return [found[key] for key in sorted(found)]


def _plain_positions(length, zone: _Zone, option: _Option, spacing: float | None) -> list[float]:
    if option.s == 0:
        if zone.kind == "whole":
            return [length / 2]
        return []
    if spacing is None:
        return []
    if zone.kind == "start":
        origin = zone.right - option.s * spacing
        return [origin + index * spacing for index in range(option.s)]
    if zone.kind == "end":
        return [zone.left + index * spacing for index in range(1, option.s + 1)]
    if zone.kind == "interior":
        return [zone.left + index * spacing for index in range(1, option.s)]
    origin = (length - option.s * spacing) / 2
    return [origin + index * spacing for index in range(option.s + 1)]


def _put(found: dict[float, Column], column: Column) -> None:
    key = round(column.y_mm, 4)
    current = found.get(key)
    if current is None or column.kind == "drive":
        found[key] = column


def _unsolvable(zone: _Zone) -> str:
    distance = _mm(zone.span)
    if zone.kind == "interior":
        return f"相邻驱动立柱相距 {distance} mm，等分后落不进 7200–9000 mm。"
    if zone.kind == "start":
        return f"起点到第一根驱动立柱 {distance} mm，放不下间距 7200–9000 mm 和悬挑 900–1500 mm。"
    if zone.kind == "end":
        return f"最后一根驱动立柱到终点 {distance} mm，放不下间距 7200–9000 mm 和悬挑 900–1500 mm。"
    return f"主梁长度 {distance} mm，放不下间距 7200–9000 mm 和两端悬挑 900–1500 mm。"


def _missing_inputs(geometry: dict) -> list[str]:
    labels = (
        ("module_length_mm", "组件长度"),
        ("module_width_mm", "组件宽度"),
        ("ground_clearance_mm", "最小离地高度"),
        ("arrangement_columns", "布置列数"),
    )
    missing = []
    for key, label in labels:
        value = geometry.get(key)
        if value is None or (isinstance(value, str) and not value.strip()):
            missing.append(label)
    return missing


def _multiples(lo: float, hi: float) -> list[float]:
    if hi < lo - _TOL:
        return []
    start = math.ceil((lo - 0.001) / ROUND_MM)
    stop = math.floor((hi + 0.001) / ROUND_MM)
    if start > stop:
        return []
    return [index * ROUND_MM for index in range(start, stop + 1)]


def _divisible(value: float) -> bool:
    return abs(value / ROUND_MM - round(value / ROUND_MM)) * ROUND_MM <= 0.001


def _floor(value: float) -> int:
    if value < 0:
        return 0
    return math.floor(value + 1e-9)


def _clamp(value: float, lo: float, hi: float) -> float:
    return min(max(value, lo), hi)


def _mm(value: float) -> str:
    if abs(value - round(value)) < 0.05:
        return str(int(round(value)))
    return f"{value:.1f}"
