"""Shared wiring for the knowledge base's document checks.

This directory holds the **executable** form of the writing constraints: F01-F08
for flow documents, and the mechanically decidable part of D02/D03 for prose.
The constraints themselves live in `_meta/`; this is their enforcer, and the two
are deliberately separate files so that changing a rule does not require
touching a test and changing a test does not silently redefine a rule.

It carries the same three guards as the project suites, for the same reason: a
run that collected nothing, a case that asserts nothing, and a case that hangs
all report success in a way indistinguishable from a real green.

What this suite does **not** do is stated in `README.md`; the undecidable
criteria (a chapter being self-sufficient, a graph being independently
readable) are listed there as human judgement rather than quietly claimed.
"""

from __future__ import annotations

import ast
import os
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _harness.paths import repository_root  # noqa: E402

CASE_TIMEOUT_SECONDS = 120.0


@pytest.fixture(scope="session")
def repo() -> Path:
    return repository_root()


def pytest_collection_modifyitems(session: pytest.Session, config: pytest.Config, items: list) -> None:
    """Refuse a run that collected nothing.

    An empty collection comes from a wrong path, a filter matching no node, or a
    tree whose checks were deleted — and pytest exits with a summary that
    automation reads as success. Collecting zero cases is never the intended
    outcome here, so it is an error rather than a pass.
    """
    if not items:
        pytest.exit(
            "collection matched zero cases: a run that exercises nothing must not read as a pass",
            returncode=1,
        )


def _module_source(func) -> str | None:
    """Return the source text of the module `func` was defined in.

    Read through `linecache`, not by opening `func.__code__.co_filename`: a
    module whose checkout has moved keeps the old absolute path in its code
    object, so opening that path fails and a guard keyed on it would judge every
    case as assertion-free.
    """
    import linecache

    filename = func.__code__.co_filename
    linecache.checkcache(filename)
    lines = linecache.getlines(filename, func.__globals__)
    return "".join(lines) if lines else None


ASSERTION_CALLABLES = {
    "pytest.raises",
    "pytest.warns",
    "pytest.fail",
    "pytest.deprecated_call",
    "raises",
    "warns",
    "fail",
    "deprecated_call",
}


def _is_assertion_call(func_node) -> bool:
    """Report whether a call node names one of pytest's asserting helpers."""
    parts = []
    node = func_node
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts)) in ASSERTION_CALLABLES


def _assert_lines(func) -> set[int]:
    """Return the source lines of `func` that assert something.

    Two forms count: an `assert` statement, and a pytest assertion context
    manager — `pytest.raises`, `pytest.warns`, `pytest.fail` — which asserts by
    the failure of its block to raise. A case using only the second form is
    asserting, and flagging it would train authors to delete the guard.

    Counting source lines rather than bytecode keeps this independent of how
    pytest rewrites assertions: the rewriting changes the opcodes, not the line
    a statement lives on. A decorated function's `co_firstlineno` is its first
    decorator, so the whole decorated span is accepted.
    """
    source_text = _module_source(func)
    if source_text is None:
        return set()
    try:
        source = ast.parse(source_text)
    except SyntaxError:
        return set()
    wanted = func.__code__.co_firstlineno
    lines: set[int] = set()
    for node in ast.walk(source):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func.__name__:
            first = min([node.lineno, *(d.lineno for d in node.decorator_list)])
            if first != wanted:
                continue
            for inner in ast.walk(node):
                if isinstance(inner, ast.Assert):
                    lines.add(inner.lineno)
                elif isinstance(inner, ast.With):
                    for item in inner.items:
                        call = item.context_expr
                        if isinstance(call, ast.Call) and _is_assertion_call(call.func):
                            lines.add(inner.lineno)
                elif isinstance(inner, ast.Call) and _is_assertion_call(inner.func):
                    lines.add(inner.lineno)
            break
    return lines


_ASSERT_HITS = 0
_MONITOR_TOOL_ID = 3
_CURRENT_CASE: list = ["", set()]


def _on_line(code, line_number):
    """Count executions of an assertion-bearing line inside the case under test."""
    global _ASSERT_HITS
    if code.co_name == _CURRENT_CASE[0] and line_number in _CURRENT_CASE[1]:
        _ASSERT_HITS += 1
    return None


def _budget_override() -> float | None:
    """Read the process-wide budget, used to verify the guard itself fires."""
    raw = os.environ.get("DSH_LINT_CASE_TIMEOUT_SECONDS")
    if raw is None:
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    return value if value > 0 else None


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item: pytest.Item):
    """Fail a case that declares no assertion, and one that overruns its budget.

    The counter instruments the case's **own** execution rather than calling it
    again: a second invocation would drop the fixtures the case declared, and
    for a case that walks the tree it would repeat the work.

    A case that fails is left alone — the failure is already reported, and
    relabelling it as "asserted nothing" would hide the real cause.
    """
    global _ASSERT_HITS, _CURRENT_CASE

    func = getattr(item, "obj", None)
    monitoring = getattr(sys, "monitoring", None)
    watching = callable(func) and monitoring is not None

    if watching:
        _ASSERT_HITS = 0
        _CURRENT_CASE = [func.__name__, _assert_lines(func)]
        monitoring.use_tool_id(_MONITOR_TOOL_ID, "assert-counter")
        monitoring.register_callback(_MONITOR_TOOL_ID, monitoring.events.LINE, _on_line)
        monitoring.set_events(_MONITOR_TOOL_ID, monitoring.events.LINE)

    started = time.monotonic()
    try:
        outcome = yield
    finally:
        if watching:
            monitoring.set_events(_MONITOR_TOOL_ID, 0)
            monitoring.free_tool_id(_MONITOR_TOOL_ID)
    elapsed = time.monotonic() - started

    if outcome.excinfo is not None:
        return

    budget = _budget_override() or CASE_TIMEOUT_SECONDS
    if elapsed > budget:
        outcome.force_exception(
            AssertionError(
                f"CASE TIMEOUT: {item.nodeid} ran for {elapsed:.1f}s, over the {budget:.0f}s budget. "
                "A case that hangs is not a case that passed."
            )
        )
        return

    if watching and _ASSERT_HITS == 0:
        declares_none = not _CURRENT_CASE[1]
        if declares_none:
            outcome.force_exception(
                AssertionError(
                    f"CASE ASSERTED NOTHING: {item.nodeid} declares no assertion at all — no "
                    "`assert`, no `pytest.raises`, and no other asserting context manager. This is "
                    "the empty-shell form the guard exists to catch."
                )
            )
