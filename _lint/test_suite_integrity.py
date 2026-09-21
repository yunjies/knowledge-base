"""Guards on the guard: the roster and the run-time checks.

Every other file here asserts something about a document. This one asserts
something about the assertions: that each check is still present and still
carries its cases, that no check exists unregistered, and that the run-time
guards in `conftest.py` are still installed.

Without it the whole set can be turned green by deleting a file — each check
guards the documents, and nothing guarded the checks.
"""

from __future__ import annotations

import ast
from pathlib import Path

# Each check and the number of asserting cases it must keep. A gate that shrank
# is a loss of protection even while its remaining cases pass, so the floor is a
# minimum rather than a target; lowering one is a deliberate statement.
GATE_FLOOR = {
    "test_flowdoc_prologue.py": 2,
    "test_flowdoc_nodes.py": 5,
    "test_flowdoc_reachability.py": 2,
    "test_flowdoc_params.py": 3,
    "test_flowdoc_blueprint.py": 2,
    "test_doc_hygiene.py": 6,
    "test_suite_integrity.py": 4,
}

# The hooks `conftest.py` must keep installing, and what each one carries.
REQUIRED_HOOKS = {
    "pytest_collection_modifyitems": "refuses a run that collected nothing",
    "pytest_runtest_call": "fails a case that declares no assertion, and one that overruns its budget",
}


def lint_dir() -> Path:
    return Path(__file__).resolve().parent


def asserting_case_count(path: Path) -> int:
    """Count module-level `test_` functions that assert something."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    count = 0
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not node.name.startswith("test_"):
            continue
        if any(isinstance(inner, ast.Assert) for inner in ast.walk(node)):
            count += 1
    return count


def test_every_registered_check_is_present_and_keeps_its_floor() -> None:
    """Each gate file must exist and still carry at least its registered cases.

    Emptying a check down to one trivial assertion leaves every other case
    passing and the suite reporting success over documents nobody is checking.
    """
    offenders = []
    for name, floor in GATE_FLOOR.items():
        path = lint_dir() / name
        if not path.is_file():
            offenders.append(f"{name} is missing — a gate that can be deleted silently guards nothing")
            continue
        found = asserting_case_count(path)
        if found < floor:
            offenders.append(f"{name} has {found} asserting case(s), below its floor of {floor}")
    assert offenders == [], "; ".join(offenders)


def test_no_check_exists_without_being_registered() -> None:
    """A check file not registered here can be deleted with nothing noticing."""
    registered = set(GATE_FLOOR)
    present = {path.name for path in lint_dir().glob("test_*.py")}
    unregistered = sorted(present - registered)
    assert unregistered == [], (
        "these checks exist but are not registered above, so deleting them would go unnoticed: "
        f"{unregistered}"
    )


def test_the_conftest_guards_are_still_installed() -> None:
    """`conftest.py` must still define the hooks that carry the run-time guards.

    The guards are why a green run means anything here; removing a hook is a
    one-line edit that no case would notice.
    """
    tree = ast.parse((lint_dir() / "conftest.py").read_text(encoding="utf-8"))
    defined = {node.name for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    missing = sorted(name for name in REQUIRED_HOOKS if name not in defined)
    assert missing == [], (
        "conftest.py no longer defines these guard hooks, so the protection they carry is gone: "
        + ", ".join(f"{name} ({REQUIRED_HOOKS[name]})" for name in missing)
    )


def test_the_case_counter_distinguishes_an_asserting_case_from_an_empty_one() -> None:
    """The floor counter must not count an empty case as a case.

    Stated over literal source so the property holds whatever the checks contain
    today: a counter returning the same number for both would let every check be
    emptied while its floor still passed.
    """
    import tempfile

    samples = {
        "def test_asserting():\n    assert 1 == 1\n": 1,
        "def test_empty():\n    x = 1\n": 0,
        "def helper():\n    assert 1 == 1\n": 0,
        "def test_two_asserts():\n    assert 1\n    assert 2\n": 1,
    }
    for source, expected in samples.items():
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as handle:
            handle.write(source)
            temp_path = Path(handle.name)
        try:
            found = asserting_case_count(temp_path)
        finally:
            temp_path.unlink()
        assert found == expected, (
            f"the counter reported {found} asserting case(s) for {source!r}, expected {expected}"
        )
