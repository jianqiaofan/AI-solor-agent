"""荷载工况和计算追溯的共同写法。"""

from typing import Any


def need(case: dict[str, Any], *path: str, label: str) -> Any:
    cursor: Any = case
    for key in path:
        if not isinstance(cursor, dict) or cursor.get(key) is None:
            raise ValueError(f"缺少{label}。")
        cursor = cursor[key]
    return cursor


def trace_step(
    trace: list[dict[str, Any]],
    formula_id: str,
    clause: str,
    expression: str,
    substitution: str,
    result: float,
    unit: str,
) -> None:
    trace.append(
        {
            "formula_id": formula_id,
            "clause": clause,
            "expression": expression,
            "substitution": substitution,
            "result": result,
            "unit": unit,
        }
    )


def load_case(
    case_id: str,
    name: str,
    value: float,
    unit: str,
    formula_id: str,
    target: str = "module",
) -> dict[str, Any]:
    return {
        "id": case_id,
        "name": name,
        "target": target,
        "value": value,
        "unit": unit,
        "formula_id": formula_id,
    }
