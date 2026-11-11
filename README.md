# 光伏跟踪支架设计流水线

各子系统通过 `contracts/` 里的 JSON 文件交接，可以单独运行。

```text
agent/                     设计助手：总对话界面。右侧结果以后再接各子系统
contracts/                 三份数据合同（设计案例、荷载、分析结果）
fixtures/                  手写的已锁定样例，荷载可以不经过抽取直接跑
products/                  以后按产品族放几何、系数表、图块规则
projects/                  每次计算的输入输出，不入库
subsystems/
  extraction/              资料抽取：客户资料 → 未锁定的 design_case.json
  loads_sap2000/           荷载 + SAP2000：已锁定案例 → loads.json → 分析结果
```

总入口是设计助手。双击仓库根目录的 `启动助手.bat`，或在激活环境后执行 `python -m agent`。对话通过 LangChain 调用 DeepSeek，密钥写在根目录 `.env` 的 `DEEPSEEK_API_KEY`。保存后刷新助手页面即可，不必改代码。

后续模块（参数确认、安装图、计算书、BOM）沿同一方式另建目录。资料抽取见 `subsystems/extraction/README.md`，荷载与 SAP2000 见 `subsystems/loads_sap2000/README.md`。

Python 环境用 Miniconda，定义在 `environment.yml`，环境名 `ai-solor-agent`。创建一次之后：

```text
conda activate ai-solor-agent
```
