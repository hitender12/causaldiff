# CausalDiff — diffs as causal graphs, not text

A code review tool that shows **why** a change matters, not just **what** changed.

## The problem

Text diffs hide semantic impact. A one-line change to a tax rate can silently
break every price, total, invoice, and test in a codebase — and a 200-line
refactor of a dead module can matter not at all. Reviewers see line counts;
they need blast radii.

## The novel idea

CausalDiff computes diffs over **data-flow and control-flow graphs** instead
of text. It parses both versions of a Python codebase into a dependency graph
(function calls plus reads/writes of module-level globals), diffs functions
and globals by source, and for each change computes the **blast radius**: the
changed node plus every function that transitively depends on it — callers,
readers of globals it writes, and the tests that cover them. Each impacted
function comes with a plain-English causal chain explaining exactly how the
change reaches it.

## Quickstart

```bash
# Compare two versions of a codebase (directories of .py files)
python -m causaldiff examples/big_blast/before examples/big_blast/after

# Or run the demo: one-line change, huge blast radius; big diff, tiny radius
python demo.py

# Run the tests
python -m unittest discover -s tests -v
```

Python 3.10+ standard library only. No dependencies to install.

## What it does

- Parses Python source with `ast` into a call graph + global data-flow graph.
- Detects changed / added / removed **functions and module-level globals**.
- Computes transitive blast radii (callers + global readers + their dependents).
- Flags which **tests** are at risk for each change.
- Explains every impact with a shortest causal chain, e.g.
  `pricing.price_of reads pricing.TAX_RATE -> cart.cart_total calls pricing.price_of`.

## Example output

One production line changed (`TAX_RATE 0.20 -> 0.25`):

```
[changed-global] pricing.TAX_RATE  (pricing.py)
  Blast radius: 11 function(s), including 5 test(s).
  Tests at risk: test_shop.test_cart_total, test_shop.test_checkout, ...
  Why: pricing.price_of reads pricing.TAX_RATE -> cart.cart_total calls pricing.price_of.
```

A ~55-line rewrite of a dead-end module: **3 functions impacted, 1 test.**

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md). Core modules:

- `causaldiff/graph.py` — AST parsing, call/data-flow graph construction.
- `causaldiff/diff.py` — version diffing, blast-radius computation, reporting.
- `causaldiff/__main__.py` — CLI.

## Honest status (v0.1.0)

What genuinely works: full pipeline on real Python codebases — graph building,
function/global diffing, transitive blast radii, test flagging, causal-chain
explanations, CLI, and the two shipped examples. 10 tests pass.

What is simplified (see ARCHITECTURE.md for detail):

- Calls are resolved by simple name; ambiguous names link to all candidates
  (over-approximation, never a missed edge).
- Dynamic dispatch, `eval`/`getattr`, decorators, and mutation of global
  mutables (`CONFIG.append(...)`) are not tracked.
- Only Python source is supported; no other languages yet.
- The "explanation" is a rendered causal chain, not a natural-language model.
- No Git integration yet — you pass two directories, not two commits.

## Evaluation plan

- **Precision/recall of breakage prediction:** on a corpus of real
  regressions, does the blast radius contain the functions whose tests
  actually failed? Target: recall ≥ 0.9, precision reported honestly.
- **Reviewer study:** time to spot the risky hunk in a PR, with vs. without
  the blast-radius report.
- **Scale:** graph build time on a 100k-line codebase.

## License

MIT. See [LICENSE](LICENSE).
