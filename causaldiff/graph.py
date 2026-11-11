"""Build call + data-flow graphs from Python source, using the ``ast`` module.

A *node* is a function (top-level or a method), identified by its qualified
name ``module[.Class].func``. Two kinds of dependency edges are recorded:

* ``calls``  -- function F calls function G (F depends on G).
* ``reads``  -- function F reads a module-level global that function G
  writes (F depends on G through shared state).

The reverse map (``dependents``) is what blast-radius analysis walks:
if G changes, every function that transitively depends on G is at risk.

Approximations, stated plainly (see ARCHITECTURE.md):
* Calls are resolved by simple name. If several functions share a name,
  edges point at all of them (over-approximation, never a missed edge).
* Dynamic dispatch, ``eval``/``getattr`` tricks and decorators are not
  resolved. Mutating a global mutable (``CONFIG.append(...)``) is not
  tracked as a write; only ``global x; x = ...`` assignments are.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field


@dataclass
class FunctionInfo:
    """One function (or method) found in the codebase."""

    name: str  # qualified name, e.g. "shop.checkout" or "shop.Cart.total"
    module: str
    file: str
    source: str  # exact source segment of the function definition
    calls: set[str] = field(default_factory=set)   # raw callee names (unqualified)
    reads: set[str] = field(default_factory=set)   # module-level globals read
    writes: set[str] = field(default_factory=set)  # module-level globals written

    @property
    def is_test(self) -> bool:
        base = self.name.rsplit(".", 1)[-1]
        return base.startswith("test_") or self.module.startswith("test_")


@dataclass
class GlobalInfo:
    """A module-level global (constant / config value)."""

    name: str  # qualified name, e.g. "pricing.TAX_RATE"
    module: str
    file: str
    source: str  # source segment of the assignment statement


@dataclass
class CodeGraph:
    """Dependency graph of one version of a codebase."""

    functions: dict[str, FunctionInfo] = field(default_factory=dict)
    globals: dict[str, GlobalInfo] = field(default_factory=dict)
    # edges[f] = {g: label} meaning "f depends on g" (label: "calls"/"reads").
    edges: dict[str, dict[str, str]] = field(default_factory=dict)
    # dependents[g] = {f : f depends on g} (reverse of edges).
    dependents: dict[str, set[str]] = field(default_factory=dict)

    def dependents_of(self, name: str) -> set[str]:
        return set(self.dependents.get(name, set()))

    def transitive_dependents(self, name: str) -> set[str]:
        """All functions that depend on ``name``, directly or indirectly."""
        seen: set[str] = set()
        stack = [name]
        while stack:
            cur = stack.pop()
            for dep in self.dependents.get(cur, set()):
                if dep not in seen:
                    seen.add(dep)
                    stack.append(dep)
        return seen

    def shortest_path(self, start: str, end: str) -> list[str] | None:
        """Shortest chain start -> ... -> end following dependents edges."""
        if start == end:
            return [start]
        prev: dict[str, str | None] = {start: None}
        queue = [start]
        while queue:
            cur = queue.pop(0)
            for nxt in sorted(self.dependents.get(cur, set())):
                if nxt not in prev:
                    prev[nxt] = cur
                    if nxt == end:
                        path = [end]
                        while prev[path[-1]] is not None:
                            path.append(prev[path[-1]])  # type: ignore[arg-type]
                        return list(reversed(path))
                    queue.append(nxt)
        return None

    def edge_label(self, user: str, used: str) -> str:
        return self.edges.get(user, {}).get(used, "depends on")


def _module_name(path: str) -> str:
    stem = path[:-3] if path.endswith(".py") else path
    parts = stem.replace("\\", "/").split("/")
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(p for p in parts if p not in ("", "."))


class _FunctionVisitor(ast.NodeVisitor):
    """Collect calls / global reads / global writes inside one function."""

    def __init__(self, module_globals: set[str]) -> None:
        self.module_globals = module_globals
        self.calls: set[str] = set()
        self.reads: set[str] = set()
        self.writes: set[str] = set()
        self._locals: set[str] = set()
        self._global_declared: set[str] = set()

    def prescan_locals(self, stmts: list[ast.stmt]) -> None:
        """Collect every name assigned anywhere in this function first.

        Python scoping makes a name local for the whole function if it is
        assigned anywhere in it, so a read before the assignment is still
        a read of a local, not of a module global. Nested functions are
        not descended into: their assignments are not this function's.
        """

        def collect(node: ast.AST) -> None:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                return
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                self._locals.add(node.id)
            if isinstance(node, ast.arg):
                self._locals.add(node.arg)
            for child in ast.iter_child_nodes(node):
                collect(child)

        for stmt in stmts:
            collect(stmt)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        # Do not descend into nested functions: they get their own node.
        return

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Lambda(self, node: ast.Lambda) -> None:
        return

    def visit_Global(self, node: ast.Global) -> None:
        self._global_declared.update(node.names)
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Store):
            if node.id in self._global_declared:
                self.writes.add(node.id)
            else:
                self._locals.add(node.id)
        elif isinstance(node.ctx, ast.Load):
            if node.id in self.module_globals and node.id not in self._locals:
                self.reads.add(node.id)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        if isinstance(func, ast.Name):
            self.calls.add(func.id)
        elif isinstance(func, ast.Attribute):
            self.calls.add(func.attr)
        self.generic_visit(node)

    def visit_arg(self, node: ast.arg) -> None:
        self._locals.add(node.arg)
        self.generic_visit(node)


def _collect_module_globals(tree: ast.Module) -> set[str]:
    globals_: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for t in targets:
                for n in ast.walk(t):
                    if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
                        globals_.add(n.id)
    return globals_


def _collect_global_infos(source: str, tree: ast.Module, module: str,
                          filename: str) -> dict[str, GlobalInfo]:
    """Module-level assignments as qualified GlobalInfo records."""
    infos: dict[str, GlobalInfo] = {}
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for t in targets:
                for n in ast.walk(t):
                    if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
                        qname = f"{module}.{n.id}"
                        infos[qname] = GlobalInfo(
                            name=qname, module=module, file=filename,
                            source=ast.get_source_segment(source, node) or "",
                        )
    return infos


def parse_source(source: str, module: str, filename: str) -> list[FunctionInfo]:
    """Parse one file's source into FunctionInfo records."""
    tree = ast.parse(source, filename=filename)
    module_globals = _collect_module_globals(tree)
    infos: list[FunctionInfo] = []

    def walk(body: list[ast.stmt], prefix: str) -> None:
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qname = f"{prefix}.{node.name}" if prefix else node.name
                visitor = _FunctionVisitor(module_globals)
                for arg in node.args.args + node.args.kwonlyargs:
                    visitor._locals.add(arg.arg)
                if node.args.vararg:
                    visitor._locals.add(node.args.vararg.arg)
                if node.args.kwarg:
                    visitor._locals.add(node.args.kwarg.arg)
                visitor.prescan_locals(node.body)
                for stmt in node.body:
                    visitor.visit(stmt)
                infos.append(
                    FunctionInfo(
                        name=qname,
                        module=module,
                        file=filename,
                        source=ast.get_source_segment(source, node) or "",
                        calls=set(visitor.calls),
                        reads=set(visitor.reads),
                        writes=set(visitor.writes),
                    )
                )
                # Nested functions become their own nodes.
                walk(node.body, qname)
            elif isinstance(node, ast.ClassDef):
                qname = f"{prefix}.{node.name}" if prefix else node.name
                walk(node.body, qname)

    walk(tree.body, module)
    return infos


def build_graph(files: dict[str, str]) -> CodeGraph:
    """Build a dependency graph from ``{relative_path: source}``."""
    graph = CodeGraph()
    for path in sorted(files):
        module = _module_name(path)
        source = files[path]
        tree = ast.parse(source, filename=path)
        graph.globals.update(_collect_global_infos(source, tree, module, path))
        for info in parse_source(source, module, path):
            graph.functions[info.name] = info

    # Resolve simple callee names to qualified names.
    by_simple: dict[str, list[str]] = {}
    for qname in graph.functions:
        by_simple.setdefault(qname.rsplit(".", 1)[-1], []).append(qname)
    # Resolve simple global names to the modules that define them.
    global_by_simple: dict[str, list[str]] = {}
    for qname in graph.globals:
        global_by_simple.setdefault(qname.rsplit(".", 1)[-1], []).append(qname)

    for info in graph.functions.values():
        deps: dict[str, str] = {}
        for callee in info.calls:
            for target in by_simple.get(callee, []):
                if target != info.name:
                    deps[target] = "calls"
        for glob in info.reads:
            for other in graph.functions.values():
                if glob in other.writes and other.name != info.name:
                    deps[other.name] = "reads"
            # Depend on the global itself, wherever it is defined.
            for gname in global_by_simple.get(glob, []):
                deps[gname] = "reads"
        graph.edges[info.name] = deps
        for target in deps:
            graph.dependents.setdefault(target, set()).add(info.name)
    return graph


def read_codebase(directory: str) -> dict[str, str]:
    """Read every ``*.py`` file under ``directory`` into ``{relpath: source}``."""
    import os

    files: dict[str, str] = {}
    for root, dirs, names in os.walk(directory):
        dirs.sort()
        for name in sorted(names):
            if name.endswith(".py"):
                full = os.path.join(root, name)
                rel = os.path.relpath(full, directory)
                with open(full, encoding="utf-8") as fh:
                    files[rel] = fh.read()
    return files
