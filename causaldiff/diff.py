"""Diff two versions of a codebase and compute causal blast radii.

A change's *blast radius* is the changed function itself plus every
function that transitively depends on it (callers, and readers of globals
it writes), in the *new* version of the graph for changed/added functions
and in the *old* version for removed functions. The report explains each
impacted function with the shortest causal chain from the change.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .graph import CodeGraph, build_graph


@dataclass
class Change:
    """One changed, added, or removed function."""

    name: str
    kind: str  # "changed" | "added" | "removed" (+ "-global" variants)
    file: str
    impact: set[str] = field(default_factory=set)  # transitive dependents + self
    tests: set[str] = field(default_factory=set)   # impacted test functions

    @property
    def impact_count(self) -> int:
        return len(self.impact)


@dataclass
class DiffResult:
    old: CodeGraph
    new: CodeGraph
    changes: list[Change]

    @property
    def total_impact(self) -> set[str]:
        out: set[str] = set()
        for c in self.changes:
            out |= c.impact
        return out

    @property
    def total_tests(self) -> set[str]:
        out: set[str] = set()
        for c in self.changes:
            out |= c.tests
        return out


def diff_codebases(old_files: dict[str, str], new_files: dict[str, str]) -> DiffResult:
    """Diff two ``{path: source}`` codebases and compute every blast radius."""
    old = build_graph(old_files)
    new = build_graph(new_files)

    old_src = {name: info.source for name, info in old.functions.items()}
    new_src = {name: info.source for name, info in new.functions.items()}

    changes: list[Change] = []
    for name in sorted(set(old_src) | set(new_src)):
        if name not in new_src:
            kind, graph = "removed", old
        elif name not in old_src:
            kind, graph = "added", new
        elif old_src[name].strip() != new_src[name].strip():
            kind, graph = "changed", new
        else:
            continue
        impact = graph.transitive_dependents(name) | {name}
        info = (new if kind != "removed" else old).functions[name]
        tests = {n for n in impact if graph.functions[n].is_test}
        changes.append(Change(name=name, kind=kind, file=info.file,
                              impact=impact, tests=tests))

    # Module-level globals: a changed constant is a change too.
    old_globs = {n: g.source for n, g in old.globals.items()}
    new_globs = {n: g.source for n, g in new.globals.items()}
    for name in sorted(set(old_globs) | set(new_globs)):
        if name not in new_globs:
            kind, graph = "removed-global", old
        elif name not in old_globs:
            kind, graph = "added-global", new
        elif old_globs[name].strip() != new_globs[name].strip():
            kind, graph = "changed-global", new
        else:
            continue
        impact = graph.transitive_dependents(name)
        info = (new if kind != "removed-global" else old).globals[name]
        tests = {n for n in impact if graph.functions[n].is_test}
        changes.append(Change(name=name, kind=kind, file=info.file,
                              impact=impact, tests=tests))
    return DiffResult(old=old, new=new, changes=changes)


def explain_chain(graph: CodeGraph, changed: str, impacted: str) -> str:
    """Plain-English causal chain from a change to an impacted function."""
    path = graph.shortest_path(changed, impacted)
    if path is None:
        return f"{impacted} is impacted by {changed} (no chain found)."
    if len(path) == 1:
        return f"{changed} itself changed."
    parts = []
    for user, used in zip(path[1:], path):
        label = graph.edge_label(user, used)
        if label == "calls":
            parts.append(f"{user} calls {used}")
        elif label == "reads":
            if used in graph.globals:
                parts.append(f"{user} reads {used}")
            else:
                parts.append(f"{user} reads a value written by {used}")
        else:
            parts.append(f"{user} depends on {used}")
    return " -> ".join(parts) + "."


def render_report(result: DiffResult, max_chains: int = 5) -> str:
    """Render a human-readable blast-radius report."""
    lines = ["CausalDiff blast-radius report", "=" * 32, ""]
    if not result.changes:
        lines.append("No function changes detected. Blast radius: 0 functions.")
        return "\n".join(lines)

    lines.append(f"Changed functions: {len(result.changes)}")
    lines.append(f"Total functions impacted: {len(result.total_impact)}")
    lines.append(f"Tests impacted: {len(result.total_tests)}")
    lines.append("")
    for change in result.changes:
        graph = result.old if change.kind.startswith("removed") else result.new
        lines.append(f"[{change.kind}] {change.name}  ({change.file})")
        lines.append(
            f"  Blast radius: {change.impact_count} function(s), "
            f"including {len(change.tests)} test(s)."
        )
        if change.tests:
            lines.append("  Tests at risk: " + ", ".join(sorted(change.tests)))
        others = sorted(n for n in change.impact if n != change.name)
        if others:
            lines.append("  Impacted: " + ", ".join(others))
        shown = 0
        for target in sorted(change.impact):
            if target == change.name:
                continue
            lines.append("  Why: " + explain_chain(graph, change.name, target))
            shown += 1
            if shown >= max_chains:
                remaining = len(change.impact) - 1 - shown
                if remaining > 0:
                    lines.append(f"  ... and {remaining} more causal chain(s).")
                break
        lines.append("")
    return "\n".join(lines)
