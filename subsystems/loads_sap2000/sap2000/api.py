"""通过本机 SAP2000 OAPI 建模、运行并读回杆件内力。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sap2000.model import SECTION

_KN_M_C = 6
_GRAVITY = 10
_FORCE_PER_LENGTH = 1


class SapSession:
    def __init__(self, program: Path) -> None:
        self.program = program
        self.model: Any = None

    def run(
        self,
        members: list[dict[str, Any]],
        cases: list[dict[str, Any]],
        combinations: list[dict[str, Any]],
        model_path: Path,
    ) -> dict[str, list[dict[str, float]]]:
        self._start()
        self._define()
        points = self._draw(members)
        self._support(members, points)
        self._loads(members, cases, combinations)
        model_path.parent.mkdir(parents=True, exist_ok=True)
        # 分析前必须先存盘。分析后再保存会解锁模型并清掉结果，所以内力要在这次保存之前读完。
        _check(self.model.File.Save(str(model_path)), "保存模型")
        self._analyze(cases)
        self._require_finished(cases)
        return self._read_forces(members, cases, combinations)

    def _start(self) -> None:
        import comtypes.client

        library = self.program.parent / "NativeAPI" / "x64" / "SAP2000v1.tlb"
        if library.is_file():
            comtypes.client.GetModule(str(library))
        import comtypes.gen.SAP2000v1 as sap

        helper = comtypes.client.CreateObject("SAP2000v1.Helper")
        helper = helper.QueryInterface(sap.cHelper)
        sap_object = helper.CreateObject(str(self.program))
        _check(sap_object.ApplicationStart(_KN_M_C, True), "启动 SAP2000")
        self.model = sap_object.SapModel

    def _define(self) -> None:
        model = self.model
        _check(model.InitializeNewModel(_KN_M_C), "初始化模型")
        _check(model.File.NewBlank(), "新建空模型")
        _check(model.SetPresentUnits(_KN_M_C), "设置单位")
        _check(model.PropMaterial.SetMaterial("EQMAT", 1), "定义材料")
        _check(model.PropMaterial.SetMPIsotropic("EQMAT", 2.0e8, 0.3, 1.2e-5), "定义弹性模量")
        _check(model.PropMaterial.SetWeightAndMass("EQMAT", 1, 0), "去掉材料自重")
        _check(
            model.PropFrame.SetGeneral(
                SECTION,
                "EQMAT",
                0.2,
                0.2,
                0.01,
                0.008,
                0.008,
                1.0e-4,
                1.0e-4,
                1.0e-4,
                1.0e-3,
                1.0e-3,
                1.0e-3,
                1.0e-3,
                0.1,
                0.1,
            ),
            "定义等刚度截面",
        )
        # 只保留所在平面内的平动和弯曲，避免一根直线模型在平面外成为机构。
        _check(model.Analyze.SetActiveDOF([False, True, True, True, False, False]), "设置平面自由度")

    def _draw(self, members: list[dict[str, Any]]) -> dict[tuple[float, float, float], str]:
        points: dict[tuple[float, float, float], str] = {}
        for member in members:
            for end in (member["i"], member["j"]):
                key = _key(end)
                if key in points:
                    continue
                name = f"P{len(points) + 1}"
                created, code = self.model.PointObj.AddCartesian(key[0], key[1], key[2], name, name)
                _check(code, f"建立节点 {name}")
                points[key] = str(created)
        for member in members:
            i_name = points[_key(member["i"])]
            j_name = points[_key(member["j"])]
            created, code = self.model.FrameObj.AddByPoint(
                i_name,
                j_name,
                member["id"],
                SECTION,
                member["id"],
            )
            _check(code, f"建立杆件 {member['id']}")
            member["sap_name"] = str(created)
            _check(
                self.model.FrameObj.SetOutputStations(str(created), 1, 0.2, 5, False, False),
                f"设置 {member['id']} 的输出点",
            )
        return points

    def _support(
        self,
        members: list[dict[str, Any]],
        points: dict[tuple[float, float, float], str],
    ) -> None:
        for member in members:
            base = member.get("base")
            if base is None:
                continue
            # UY、UZ 固定，平面内转角放开。
            _check(
                self.model.PointObj.SetRestraint(
                    points[_key(base)],
                    [False, True, True, False, False, False],
                ),
                f"设置 {member['id']} 柱脚铰接",
            )

    def _loads(
        self,
        members: list[dict[str, Any]],
        cases: list[dict[str, Any]],
        combinations: list[dict[str, Any]],
    ) -> None:
        model = self.model
        beams = [item for item in members if item["role"] == "beam"]
        for case in cases:
            _check(
                model.LoadPatterns.Add(case["id"], case["pattern"], 0, True),
                f"建立荷载工况 {case['id']}",
            )
            for beam in beams:
                _check(
                    model.FrameObj.SetLoadDistributed(
                        beam["sap_name"],
                        case["id"],
                        _FORCE_PER_LENGTH,
                        _GRAVITY,
                        0,
                        1,
                        case["value"],
                        case["value"],
                        "Global",
                        True,
                        True,
                    ),
                    f"把 {case['id']} 加到 {beam['id']}",
                )
        for combo in combinations:
            _check(model.RespCombo.Add(combo["id"], 0), f"建立组合 {combo['id']}")
            for factor in combo["factors"]:
                _check(
                    model.RespCombo.SetCaseList(combo["id"], 0, factor["case_id"], factor["factor"]),
                    f"写入组合 {combo['id']}",
                )

    def _analyze(self, cases: list[dict[str, Any]]) -> None:
        model = self.model
        _check(model.Analyze.SetRunCaseFlag("", False, True), "关闭默认分析工况")
        for case in cases:
            _check(model.Analyze.SetRunCaseFlag(case["id"], True, False), f"准备运行 {case['id']}")
        _check(model.Analyze.RunAnalysis(), "运行分析")

    def _require_finished(self, cases: list[dict[str, Any]]) -> None:
        status = self.model.Analyze.GetCaseStatus(0, [], [])
        names = list(status[1])
        values = [int(item) for item in status[2]]
        wanted = {case["id"] for case in cases}
        failed = [name for name, value in zip(names, values) if name in wanted and value != 4]
        if failed:
            raise RuntimeError("这些工况没有算完：" + "、".join(failed))

    def _read_forces(
        self,
        members: list[dict[str, Any]],
        cases: list[dict[str, Any]],
        combinations: list[dict[str, Any]],
    ) -> dict[str, list[dict[str, float]]]:
        setup = self.model.Results.Setup
        _check(setup.DeselectAllCasesAndCombosForOutput(), "清空结果选择")
        for case in cases:
            _check(setup.SetCaseSelectedForOutput(case["id"], True), f"选择工况 {case['id']}")
        for combo in combinations:
            _check(setup.SetComboSelectedForOutput(combo["id"], True), f"选择组合 {combo['id']}")
        found: dict[str, list[dict[str, float]]] = {}
        for member in members:
            found[member["id"]] = _frame_rows(self.model, member["sap_name"])
        return found


def _frame_rows(model: Any, name: str) -> list[dict[str, float]]:
    result = model.Results.FrameForce(name, 0, 0, [], [], [], [], [], [], [], [], [], [], [], [], [])
    if not isinstance(result, (tuple, list)) or len(result) < 15:
        raise RuntimeError(f"读不到 {name} 的内力。")
    count = int(result[0])
    p, v2, v3, t, m2, m3, code = result[8], result[9], result[10], result[11], result[12], result[13], result[14]
    _check(code, f"读取 {name} 的内力")
    if count <= 0:
        raise RuntimeError(f"{name} 没有内力结果。")
    rows = []
    for index in range(count):
        rows.append(
            {
                "P": float(p[index]),
                "V2": float(v2[index]),
                "V3": float(v3[index]),
                "T": float(t[index]),
                "M2": float(m2[index]),
                "M3": float(m3[index]),
            }
        )
    return rows


def _key(point: tuple[float, float, float]) -> tuple[float, float, float]:
    return tuple(round(float(value), 6) for value in point)


def _check(result: Any, action: str) -> None:
    code = result[-1] if isinstance(result, tuple) else result
    if isinstance(code, int) and code != 0:
        raise RuntimeError(f"{action}失败，SAP2000 返回 {code}。")
