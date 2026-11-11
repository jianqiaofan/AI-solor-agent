"""荷载子系统命令行。"""

import argparse
import json
import sys
from pathlib import Path

from loads.pipeline import build_loads


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="loads",
        description="读取已锁定的 design_case.json，写出 loads.json。",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="由设计案例生成荷载文件")
    run.add_argument("-i", "--input", required=True, help="design_case.json 路径")
    run.add_argument("-o", "--output", required=True, help="loads.json 输出路径")
    args = parser.parse_args(argv)
    try:
        design_case = json.loads(Path(args.input).read_text(encoding="utf-8"))
        loads = build_loads(design_case)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(loads, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
