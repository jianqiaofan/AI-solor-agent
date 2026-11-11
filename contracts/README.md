# 数据合同

子系统之间只通过这三份 JSON 交接。模式文件在 `schemas/`，版本号为 `1.0.0`。

| 文件 | 模式 | 谁写出 | 谁读取 |
|---|---|---|---|
| `design_case.json` | `design_case.schema.json` | 资料抽写出 `draft`；人工确认后改为 `confirmed`。手写样例可直接标成 `confirmed` | 荷载、SAP2000 |
| `loads.json` | `loads.schema.json` | 荷载 | SAP2000、计算书 |
| `analysis_result.json` | `analysis_result.schema.json` | SAP2000 | 安装图、计算书、BOM |

`site`、`geometry`、`materials` 的属性对应固定倾角资料表 Design Data Collection Sheet 的全部字段，顶层字段保持不变。每个属性都必须出现；资料未填写或这一步尚未识别时为 `null`。`site.wind_speed_averaging` 不在资料表上，确认时按 `site.design_code` 选择。`code_pack` 与 `site.design_code` 取同一个规范名称，尚未识别时同样为 `null`。

荷载命令只处理 `status` 为 `confirmed` 的设计案例。样例见 `fixtures/design_case.sample.json`，其中的 `null` 是占位，不是设计输入。

一次计算建议落在：

```text
projects/{项目}/{修订}/
  design_case.json
  loads.json
  analysis_result.json
  sap/                  # 模型与 SAP2000 运行文件
  manifest.json         # 输入校验值、命令版本、时间
```

`projects/` 下的计算结果不入库。
