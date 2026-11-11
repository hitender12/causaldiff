"""CausalDiff: diffs as causal graphs, not text."""

from .diff import Change, DiffResult, diff_codebases, explain_chain, render_report
from .graph import CodeGraph, FunctionInfo, GlobalInfo, build_graph, read_codebase

__all__ = [
    "Change",
    "CodeGraph",
    "DiffResult",
    "FunctionInfo",
    "GlobalInfo",
    "build_graph",
    "diff_codebases",
    "explain_chain",
    "read_codebase",
    "render_report",
]

__version__ = "0.1.0"
