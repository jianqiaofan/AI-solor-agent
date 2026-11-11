# 子模块 1：荷载 + SAP2000

这一步在业务上是一次结构计算，目录内分成两个可以单独运行的程序。荷载不依赖 SAP2000；SAP2000 只读已经生成的 `loads.json`。

```text
loads_sap2000/
  loads/                 # python -m loads
    pipeline.py          # 串接计算工具的位置
    tools/               # 荷载计算公式放这里
    tests/
  sap2000/               # python -m sap2000
    runner.py            # 打开模板、写入荷载、运行、读回结果
    skill/               # 放置你提供的 SKILL.md
    templates/           # SAP2000 模板模型
    tests/
```

共享合同在仓库的 `contracts/schemas/`。

## 荷载

在本目录执行：

```text
python -m loads run -i ..\..\fixtures\design_case.sample.json -o ..\..\projects\SAMPLE\r0\loads.json
```

命令计算组件自重、速度风压和屋面雪荷载，并写出 `loads.json`。计算公式在 `loads/tools/`。输入案例的 `status` 必须是 `confirmed`，风速时距必须是 `3 s gust`。

## SAP2000

把建模 skill 存为 `sap2000/skill/SKILL.md`，模板模型放到 `sap2000/templates/`。实现写在 `sap2000/runner.py` 的 `run_analysis`。

若希望在 Cursor 对话里自动用到这份 skill，再复制一份到仓库的 `.cursor/skills/sap2000-modeling/SKILL.md`。`.cursor/skills/` 是项目技能的加载位置，子系统目录里的副本随本模块一起保存。

```text
python -m sap2000 run ^
  -i ..\..\projects\SAMPLE\r0\design_case.json ^
  -l ..\..\projects\SAMPLE\r0\loads.json ^
  -o ..\..\projects\SAMPLE\r0\analysis_result.json ^
  --workdir ..\..\projects\SAMPLE\r0\sap
```
