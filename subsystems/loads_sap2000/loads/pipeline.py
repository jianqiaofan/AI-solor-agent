"""把已锁定的设计案例串成组件面荷载。"""

from typing import Any

from loads.tools import dead, snow, wind
from loads.tools.combinations import strength_combinations


def build_loads(design_case: dict[str, Any]) -> dict[str, Any]:
    """返回符合 contracts/schemas/loads.schema.json 的对象。

    给出组件自重、0° 和 60° 的风荷载、0° 雪荷载，以及强度设计组合。
    """
    if design_case.get("status") != "confirmed":
        raise ValueError("荷载计算只接受 status 为 confirmed 的 design_case。")
    trace: list[dict[str, Any]] = []
    cases: list[dict[str, Any]] = []
    cases += dead.build(design_case, trace)
    cases += wind.build(design_case, trace)
    cases += snow.build(design_case, trace)
    return {
        "schema_version": "1.0.0",
        "design_case_revision": design_case["revision"],
        "cases": cases,
        "combinations": strength_combinations(cases),
        "trace": trace,
    }
