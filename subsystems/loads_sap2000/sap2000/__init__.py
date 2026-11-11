"""SAP2000 子系统。输入 design_case.json 与 loads.json，输出 analysis_result.json。"""

from sap2000.runner import run_analysis

__all__ = ["run_analysis"]
