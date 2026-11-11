"""SAP2000 子系统命令行。"""

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="sap2000",
        description="读取 design_case.json 与 loads.json，写出 analysis_result.json。",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="按模板建模并运行分析")
    run.add_argument("-i", "--input", required=True, help="design_case.json 路径")
    run.add_argument("-l", "--loads", required=True, help="loads.json 路径")
    run.add_argument("-o", "--output", required=True, help="analysis_result.json 输出路径")
    run.add_argument(
        "--workdir",
        required=True,
        help="本次 SAP2000 模型的工作目录，例如 projects/{项目}/{修订}/sap",
    )
    args = parser.parse_args(argv)

    print(
        "已接收设计案例 {input}、荷载 {loads}，计划写出 {output}（工作目录 {workdir}）。"
        "建模 skill 尚未接入。".format(
            input=args.input,
            loads=args.loads,
            output=args.output,
            workdir=args.workdir,
        ),
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
