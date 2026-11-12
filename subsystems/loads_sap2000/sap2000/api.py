"""通过本机 SAP2000 OAPI 建模、运行并读回杆件内力。

build 建一次模型：材料、截面表里的全部截面、杆件、柱脚、荷载和组合。
solve 按给定的截面分配运行一次分析，可以反复调用。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

_KN_M_C = 6
_GRAVITY = 10
_FORCE_PER_LENGTH = 1
_STEEL = 1
_WEIGHT_PER_VOLUME = 1
_G = 9.80665


class SapSession:
    def __init__(self, program: Path) -> None:
        self.program = program
        self.model: Any = None
        self._members: list[dict[str, Any]] = []
        self._cases: list[dict[str, Any]] = []
        self._combinations: list[dict[str, Any]] = []
        self._model_path: Path | None = None
        self._analyzed = False

    def build(
        self,
        members: list[dict[str, Any]],
        cases: list[dict[str, Any]],
        combinations: list[dict[str, Any]],
        table: dict[str, Any],
        model_path: Path,
    ) -> None:
        self._members = members
        self._cases = cases
        self._combinations = combinations
        self._model_path = model_path
        self._start()
        self._define(table)
        points = self._draw(members)
        self._support(members, points)
        self._loads(members, cases, combinations)

    def solve(self, assignment: dict[str, str]) -> dict[str, list[dict[str, Any]]]:
        model = self.model
        if self._analyzed:
            _check(model.SetModelIsLocked(False), "解锁模型")
        for member in self._members:
            _check(
                model.FrameObj.SetSection(member["sap_name"], assignment[member["id"]], 0),
                f"给 {member['id']} 指定截面",
            )
        assert self._model_path is not None
        self._model_path.parent.mkdir(parents=True, exist_ok=True)
        # 分析前必须先存盘。分析后再保存会解锁模型并清掉结果，所以内力要在下一次保存之前读完。
        _check(model.File.Save(str(self._model_path)), "保存模型")
        self._analyze(self._cases)
        self._require_finished(self._cases)
        self._analyzed = True
        return self._read_forces(self._members, self._cases, self._combinations)

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

    def _define(self, table: dict[str, Any]) -> None:
        model = self.model
        material = table["material"]
        name = str(material["name"])
        _check(model.InitializeNewModel(_KN_M_C), "初始化模型")
        _check(model.File.NewBlank(), "新建空模型")
        _check(model.SetPresentUnits(_KN_M_C), "设置单位")
        _check(model.PropMaterial.SetMaterial(name, _STEEL), f"定义材料 {name}")
        _check(
            model.PropMaterial.SetMPIsotropic(
                name,
                float(material["E_mpa"]) * 1e3,
                float(material["poisson"]),
                float(material["thermal_expansion"]),
            ),
            f"定义 {name} 的弹性模量",
        )
        weight = float(material["density_kg_m3"]) * _G / 1000.0
        _check(model.PropMaterial.SetWeightAndMass(name, _WEIGHT_PER_VOLUME, weight), f"定义 {name} 的重度")
        depth = float(table["across_flats_mm"]) / 1000.0
        for section in table["sections"]:
            area = float(section["area_mm2"]) * 1e-6
            shear = float(section["shear_area_mm2"]) * 1e-6
            inertia = float(section["I_mm4"]) * 1e-12
            elastic = float(section["W_el_corner_mm3"]) * 1e-9
            plastic = float(section["W_pl_corner_mm3"]) * 1e-9
            radius = float(section["radius_of_gyration_mm"]) / 1000.0
            _check(
                model.PropFrame.SetGeneral(
                    section["name"],
                    name,
                    depth,
                    depth,
                    area,
                    shear,
                    shear,
                    float(section["torsion_constant_mm4"]) * 1e-12,
                    inertia,
                    inertia,
                    elastic,
                    elastic,
                    plastic,
                    plastic,
                    radius,
                    radius,
                ),
                f"定义截面 {section['name']}",
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
                member["section"],
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
                model.LoadPatterns.Add(case["id"], case["pattern"], float(case.get("self_weight", 0)), True),
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
    ) -> dict[str, list[dict[str, Any]]]:
        setup = self.model.Results.Setup
        _check(setup.DeselectAllCasesAndCombosForOutput(), "清空结果选择")
        for case in cases:
            _check(setup.SetCaseSelectedForOutput(case["id"], True), f"选择工况 {case['id']}")
        for combo in combinations:
            _check(setup.SetComboSelectedForOutput(combo["id"], True), f"选择组合 {combo['id']}")
        found: dict[str, list[dict[str, Any]]] = {}
        for member in members:
            found[member["id"]] = _frame_rows(self.model, member["sap_name"])
        return found


def _frame_rows(model: Any, name: str) -> list[dict[str, Any]]:
    result = model.Results.FrameForce(name, 0, 0, [], [], [], [], [], [], [], [], [], [], [], [], [])
    if not isinstance(result, (tuple, list)) or len(result) < 15:
        raise RuntimeError(f"读不到 {name} 的内力。")
    count = int(result[0])
    case = result[5]
    p, v2, v3, t, m2, m3, code = result[8], result[9], result[10], result[11], result[12], result[13], result[14]
    _check(code, f"读取 {name} 的内力")
    if count <= 0:
        raise RuntimeError(f"{name} 没有内力结果。")
    rows = []
    for index in range(count):
        rows.append(
            {
                "case": str(case[index]),
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
