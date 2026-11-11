# CausalDiff architecture

## Data model

```
CodeGraph
  functions:  {qualified_name -> FunctionInfo}   # module[.Class].func
  globals:    {qualified_name -> GlobalInfo}     # module.CONSTANT
  edges:      {f -> {g: "calls" | "reads"}}       # f depends on g
  dependents: {g -> {f}}                          # reverse of edges
```

A `FunctionInfo` records the function's exact source segment, the names it
calls, and the module-level globals it reads and writes (via `global`
declarations). A `GlobalInfo` records a module-level assignment's source.

## Pipeline

1. **Parse** (`graph.parse_source`): `ast.parse` per file. A visitor
   collects calls (by callee name, including `obj.method` attribute calls),
   global reads, and global writes. A pre-scan collects all locally assigned
   names first, because Python scoping makes a name local for the whole
   function even if it is read before assignment.
2. **Resolve** (`graph.build_graph`): simple callee/global names are mapped
   to qualified names. Ambiguous names resolve to *all* candidates
   (over-approximation). Two edge kinds are built:
   - `calls`: F calls G.
   - `reads`: F reads a global that G writes, or reads the global itself.
3. **Diff** (`diff.diff_codebases`): function sources and global assignment
   sources are compared textually (stripped). Changed / added / removed
   nodes are collected.
4. **Blast radius**: for each change, BFS over `dependents` from the changed
   node (in the new graph for changed/added, the old graph for removed).
   The changed node itself is included. Impacted tests are the radius
   members whose name or module starts with `test_`.
5. **Explain** (`diff.explain_chain`): BFS shortest path from the changed
   node to each impacted node, rendered as a chain of `calls` / `reads`
   steps.

## Why this design

- **Static only, no execution.** The tool runs on code that does not import
  cleanly and never executes untrusted code — only `ast.parse`.
- **Over-approximate, never under-approximate.** A missed edge means a
  missed breakage, the worst failure mode for this tool. Ambiguity therefore
  links to all candidates.
- **Functions and globals are both first-class change units.** A changed
  constant is often the highest-impact one-line change in a codebase.

## Known limitations (honest)

- Name-based call resolution: `self.method()`, aliased imports, and
  same-named functions in different modules can create spurious edges.
- No inter-procedural data flow beyond module globals (no aliasing, no
  object fields, no closures captured across functions).
- No dynamic behavior: `eval`, `getattr`, decorators, metaclasses,
  monkey-patching are invisible.
- Mutation of a global mutable (`CONFIG["x"] = 1`, `CACHE.append(v)`) is not
  a tracked write.
- Python only. The graph layer is language-specific by design; a
  tree-sitter backend is the planned route to other languages.

## Future work

- Git integration (`causaldiff HEAD~1 HEAD`), per-PR output, CI action.
- Execution-trace validation: run the test suite and compare predicted vs.
  actual failing tests (the evaluation in the README).
- Type-aware resolution using annotations and import graphs.
- tree-sitter backend for JavaScript/TypeScript, Go, Rust.
