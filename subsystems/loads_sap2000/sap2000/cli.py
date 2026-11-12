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
    sections = sub.add_parser("sections", help="向正八角管截面表追加厚度，已有的厚度不动")
    sections.add_argument("--table", help="截面表路径，默认 products/qizhuo30/sections/secton-octagon-165.json")
    sections.add_argument("--across-flats", type=float, default=165.0, help="对边距离，mm")
    sections.add_argument("--from", dest="first", type=float, required=True, help="起始壁厚，mm")
    sections.add_argument("--to", dest="last", type=float, help="终止壁厚，mm，缺省时只加起始壁厚")
    sections.add_argument("--step", type=float, default=0.1, help="步距，mm")
    args = parser.parse_args(argv)

    if args.command == "sections":
        from pathlib import Path

        from sap2000.runner import SECTION_TABLE
        from sap2000.sections import add_octagon_sections, thickness_steps

        table = Path(args.table) if args.table else SECTION_TABLE
        last = args.first if args.last is None else args.last
        added = add_octagon_sections(table, args.across_flats, thickness_steps(args.first, last, args.step))
        print("新加：" + ("、".join(added) if added else "没有，表里已经都有"))
        return 0

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
