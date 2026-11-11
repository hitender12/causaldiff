"""Command line: python -m causaldiff <old_dir> <new_dir>"""

import sys

from .diff import diff_codebases, render_report
from .graph import read_codebase


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 2:
        print("usage: python -m causaldiff <old_dir> <new_dir>", file=sys.stderr)
        return 2
    old_files = read_codebase(args[0])
    new_files = read_codebase(args[1])
    result = diff_codebases(old_files, new_files)
    print(render_report(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
