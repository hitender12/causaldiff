"""Demo: the two headline cases for CausalDiff.

1. big_blast   -- one production line changes (TAX_RATE 0.20 -> 0.25)
                  and the blast radius covers the whole shop.
2. small_blast -- ~55 lines rewritten in a dead-end module, and almost
                  nothing is impacted.

Run: python demo.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from causaldiff import diff_codebases, render_report
from causaldiff.graph import read_codebase

HERE = os.path.dirname(os.path.abspath(__file__))


def show(title, before_dir, after_dir, note):
    print("=" * 70)
    print(title)
    print("=" * 70)
    print(note)
    print()
    result = diff_codebases(read_codebase(before_dir), read_codebase(after_dir))
    print(render_report(result))


def main():
    show(
        "CASE 1: one line changed, huge blast radius",
        os.path.join(HERE, "examples", "big_blast", "before"),
        os.path.join(HERE, "examples", "big_blast", "after"),
        "Production change: TAX_RATE 0.20 -> 0.25 (one line in pricing.py).\n"
        "The tests were updated to the new expected values; CausalDiff\n"
        "reports which tests the change invalidates and why.",
    )
    show(
        "CASE 2: big diff, tiny blast radius",
        os.path.join(HERE, "examples", "small_blast", "before"),
        os.path.join(HERE, "examples", "small_blast", "after"),
        "Change: the legacy report exporter rewritten (~55 lines across\n"
        "two functions). Nothing in the live system calls it.",
    )


if __name__ == "__main__":
    main()
