"""资料抽取子系统命令行。"""

import argparse
import json
import sys
from pathlib import Path

from extraction.parsers.collection_sheet import AmbiguousCollectionSheet, CollectionSheetNotFound
from extraction.pipeline import extract_design_case, parse_documents
from extraction.tools.design_case import write_design_case


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="extraction",
        description="读取客户资料，写出 design_case.json。",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="由资料目录生成草稿设计案例，不打开界面")
    run.add_argument("-i", "--input", required=True, help="客户资料目录")
    run.add_argument("-o", "--output", required=True, help="design_case.json 输出路径")
    run.add_argument(
        "--workdir",
        required=True,
        help="解析产物目录，例如 projects/{项目}/{修订}/parsed",
    )
    sub.add_parser("ui", help="打开选择文件、核对和确认的工作界面")

    args = parser.parse_args(argv)
    if args.command == "ui":
        from extraction.ui.app import main as ui_main

        return ui_main()

    try:
        source = Path(args.input)
        work_dir = Path(args.workdir)
        parse_documents(source, work_dir)
        case = extract_design_case(work_dir)
        output = Path(args.output)
        write_design_case(case, output)
    except (CollectionSheetNotFound, AmbiguousCollectionSheet, ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(json.dumps({"output": str(Path(args.output)), "status": case["status"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
