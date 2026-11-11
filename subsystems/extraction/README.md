# 子模块：资料抽取

读取客户提资，写出 `design_case.json`。不修改荷载参数，也不调用 SAP2000。

```text
extraction/
  pipeline.py            # 先解析，再抽取
  parsers/               # 资料表 PDF
  tools/                 # 装配 design_case
  ui/                    # 选择文件、核对、确认
  tests/
```

输出必须符合 `contracts/schemas/design_case.schema.json`。资料表上的每个字段都要写出，表单空白或尚未识别的项用 `null` 占位。`parameters` 里来自资料的项用 `extracted` 并写下 `source`，用户在窗体里改过的项用 `confirmed`。风速时距不在资料表上，核对窗体按所选设计规范列出可选时距，写入 `site.wind_speed_averaging`，并标为 `confirmed`。

使用仓库根目录的 conda 环境 `ai-solor-agent`。在本目录打开工作界面：

```text
conda activate ai-solor-agent
python -m extraction ui
```

界面里选择或拖入提资文件，确认后按资料表版式核对。底部的「确认」会把 `design_case.json` 写到 `projects/{项目编号}/{修订}/`，`status` 为 `confirmed`。

不打开界面、只生成草稿时：

```text
python -m extraction run ^
  -i <客户资料目录> ^
  -o ..\..\projects\SAMPLE\r0\design_case.json ^
  --workdir ..\..\projects\SAMPLE\r0\parsed
```

`run` 的 `status` 保持 `draft`。人工确认仍以界面为准，荷载子系统只接收 `confirmed`。

`fixtures/design_case.sample.json` 仍是手写的已锁定样例，供荷载子系统单独运行，不是本模块的输出。
