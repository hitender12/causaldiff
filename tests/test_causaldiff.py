"""Tests for CausalDiff. Run: python -m unittest discover -s tests -v"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from causaldiff import diff_codebases, explain_chain, render_report
from causaldiff.graph import build_graph, read_codebase

HERE = os.path.dirname(__file__)
EXAMPLES = os.path.join(HERE, "..", "examples")

SHOP_BEFORE = {
    "pricing.py": 'TAX_RATE = 0.20\n\ndef price_of(item):\n    return round(item["price"] * (1 + TAX_RATE), 2)\n',
    "cart.py": 'from pricing import price_of\n\ndef cart_total(cart):\n    return round(sum(price_of(i) for i in cart), 2)\n',
    "checkout.py": 'from cart import cart_total\n\ndef checkout(cart):\n    return {"total": cart_total(cart)}\n',
    "test_shop.py": 'from pricing import price_of\nfrom cart import cart_total\nfrom checkout import checkout\n\ndef test_price():\n    assert price_of({"price": 100}) == 120.0\n\ndef test_total():\n    assert cart_total([{"price": 100}]) == 120.0\n\ndef test_checkout():\n    assert checkout([{"price": 100}])["total"] == 120.0\n',
}


def with_tax(codebase, rate):
    out = dict(codebase)
    out["pricing.py"] = codebase["pricing.py"].replace("0.20", rate)
    return out


class TestBlastRadius(unittest.TestCase):
    def test_one_line_change_large_blast_radius(self):
        """One changed constant ripples through the whole shop."""
        result = diff_codebases(SHOP_BEFORE, with_tax(SHOP_BEFORE, "0.25"))
        self.assertEqual(len(result.changes), 1)
        change = result.changes[0]
        self.assertEqual(change.name, "pricing.TAX_RATE")
        self.assertEqual(change.kind, "changed-global")
        for expected in (
            "pricing.price_of",
            "cart.cart_total",
            "checkout.checkout",
            "test_shop.test_price",
            "test_shop.test_total",
            "test_shop.test_checkout",
        ):
            self.assertIn(expected, change.impact, f"{expected} should be impacted")
        self.assertEqual(len(change.tests), 3)

    def test_big_diff_tiny_blast_radius(self):
        """A 40-line rewrite of an uncalled function barely matters."""
        before = {
            "legacy.py": (
                "def format_report(rows):\n"
                + "".join(f"    # line {i} of the old formatter\n" for i in range(40))
                + "    return 'old'\n"
            ),
            "test_legacy.py": (
                "from legacy import format_report\n\n"
                "def test_report():\n    assert format_report([]) == 'old'\n"
            ),
        }
        after = dict(before)
        after["legacy.py"] = (
            "def format_report(rows):\n"
            + "".join(f"    # rewritten line {i}\n" for i in range(45))
            + "    return 'new'\n"
        )
        result = diff_codebases(before, after)
        changed = [c for c in result.changes if c.name == "legacy.format_report"]
        self.assertEqual(len(changed), 1)
        # Only the function itself and its one test are impacted.
        self.assertEqual(changed[0].impact, {"legacy.format_report", "test_legacy.test_report"})
        self.assertEqual(len(changed[0].tests), 1)

    def test_removed_function_flags_callers(self):
        before = {
            "a.py": "def helper():\n    return 1\n\ndef user():\n    return helper()\n",
        }
        after = {"a.py": "def user():\n    return 0\n"}
        result = diff_codebases(before, after)
        removed = [c for c in result.changes if c.kind == "removed"]
        self.assertEqual([c.name for c in removed], ["a.helper"])
        self.assertIn("a.user", removed[0].impact)

    def test_no_changes_empty_diff(self):
        result = diff_codebases(SHOP_BEFORE, dict(SHOP_BEFORE))
        self.assertEqual(result.changes, [])
        self.assertEqual(result.total_impact, set())

    def test_global_write_read_edge(self):
        """A writes a global, B reads it: changing A puts B in the radius."""
        before = {
            "state.py": (
                "MODE = 'off'\n\n"
                "def set_mode(m):\n    global MODE\n    MODE = m\n\n"
                "def describe():\n    return f'mode is {MODE}'\n"
            ),
        }
        after = dict(before)
        after["state.py"] = before["state.py"].replace("MODE = m", "MODE = m.upper()")
        result = diff_codebases(before, after)
        changed = [c for c in result.changes if c.name == "state.set_mode"]
        self.assertEqual(len(changed), 1)
        self.assertIn("state.describe", changed[0].impact)

    def test_explanation_names_the_chain(self):
        result = diff_codebases(SHOP_BEFORE, with_tax(SHOP_BEFORE, "0.25"))
        chain = explain_chain(result.new, "pricing.TAX_RATE", "checkout.checkout")
        self.assertIn("pricing.TAX_RATE", chain)
        self.assertIn("checkout.checkout", chain)
        self.assertIn("calls", chain)


class TestShippedExamples(unittest.TestCase):
    def test_big_blast_example(self):
        result = diff_codebases(
            read_codebase(os.path.join(EXAMPLES, "big_blast", "before")),
            read_codebase(os.path.join(EXAMPLES, "big_blast", "after")),
        )
        tax = [c for c in result.changes if c.name == "pricing.TAX_RATE"]
        self.assertEqual(len(tax), 1)
        # 6 production functions + 5 tests.
        self.assertEqual(len(tax[0].impact), 11)
        self.assertEqual(len(tax[0].tests), 5)

    def test_small_blast_example(self):
        result = diff_codebases(
            read_codebase(os.path.join(EXAMPLES, "small_blast", "before")),
            read_codebase(os.path.join(EXAMPLES, "small_blast", "after")),
        )
        # ~55 lines changed, but at most 3 functions are impacted.
        self.assertLessEqual(len(result.total_impact), 3)
        self.assertEqual(len(result.total_tests), 1)

    def test_report_renders(self):
        result = diff_codebases(
            read_codebase(os.path.join(EXAMPLES, "big_blast", "before")),
            read_codebase(os.path.join(EXAMPLES, "big_blast", "after")),
        )
        text = render_report(result)
        self.assertIn("pricing.TAX_RATE", text)
        self.assertIn("Blast radius", text)


class TestGraph(unittest.TestCase):
    def test_call_graph_basics(self):
        graph = build_graph({
            "a.py": "def f():\n    return g()\n\ndef g():\n    return 1\n",
        })
        self.assertEqual(graph.edges["a.f"], {"a.g": "calls"})
        self.assertEqual(graph.transitive_dependents("a.g"), {"a.f"})


if __name__ == "__main__":
    unittest.main()
