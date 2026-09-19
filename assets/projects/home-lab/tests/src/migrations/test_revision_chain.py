"""Mirrors `migrations/`: revision chain integrity and schema coverage."""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from _harness.paths import repository_root

VERSIONS = "migrations/versions"


def _revision_files(repo: Path) -> list[Path]:
    return sorted((repo / VERSIONS).glob("*.py"))


def _read_constant(path: Path, name: str) -> str | None:
    """Read a module-level constant, whether annotated or plain."""
    tree = ast.parse(path.read_text())
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == name and node.value is not None:
                return ast.literal_eval(node.value)
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return ast.literal_eval(node.value)
    return None


def test_migration_directory_holds_revisions(repo: Path) -> None:
    assert _revision_files(repo), "no migration revisions found"


def test_every_revision_declares_a_revision_id(repo: Path) -> None:
    for path in _revision_files(repo):
        assert _read_constant(path, "revision"), f"{path.name} declares no revision"


def test_revision_ids_are_unique(repo: Path) -> None:
    ids = [_read_constant(path, "revision") for path in _revision_files(repo)]
    assert len(ids) == len(set(ids)), f"duplicate revision ids: {ids}"


def test_revision_chain_has_exactly_one_root(repo: Path) -> None:
    downs = {_read_constant(path, "down_revision") for path in _revision_files(repo)}
    roots = [down for down in downs if down is None]
    assert len(roots) == 1, f"expected one root revision, found {len(roots)}"


MISSING_ANCESTOR = "0009_provider_connection_status"


def test_every_down_revision_resolves(repo: Path) -> None:
    """No revision may point at a parent that does not exist.

    `0010_provider_platform_catalog` declares `0009_provider_connection_status`
    as its parent, and that revision is not in the checkout. The chain is
    therefore broken, so `alembic upgrade head` cannot reach 0010. This test
    pins that fact; restoring 0009 makes it pass.
    """
    ids = {_read_constant(path, "revision") for path in _revision_files(repo)}
    dangling = {}
    for path in _revision_files(repo):
        down = _read_constant(path, "down_revision")
        if down is None:
            continue
        parents = down if isinstance(down, (list, tuple)) else [down]
        missing = [parent for parent in parents if parent not in ids]
        if missing:
            dangling[path.name] = missing

    assert dangling == {"0010_provider_platform_catalog.py": [MISSING_ANCESTOR]}, (
        "the set of revisions with unresolvable parents changed: "
        f"{dangling}"
    )


def test_chain_is_fully_linked(repo: Path) -> None:
    """Record which revisions no other revision descends from.

    Two revisions are unreferenced in this checkout: `0007_jellyfin_library_identity`,
    which sits off the linear chain, and `0010_provider_platform_catalog`, which
    dangles because its declared parent is absent.
    """
    ids = {_read_constant(path, "revision") for path in _revision_files(repo)}
    referenced: set[str] = set()
    for path in _revision_files(repo):
        down = _read_constant(path, "down_revision")
        if down is None:
            continue
        referenced.update(down if isinstance(down, (list, tuple)) else [down])
    roots = {
        _read_constant(path, "revision")
        for path in _revision_files(repo)
        if _read_constant(path, "down_revision") is None
    }
    orphaned = ids - referenced - roots
    assert orphaned == {
        "0007_jellyfin_library_identity",
        "0010_provider_platform_catalog",
    }, f"the set of unreferenced revisions changed: {orphaned}"


def test_revisions_only_define_upgrade_and_downgrade(repo: Path) -> None:
    for path in _revision_files(repo):
        tree = ast.parse(path.read_text())
        functions = {
            node.name for node in tree.body if isinstance(node, ast.FunctionDef)
        }
        assert {"upgrade", "downgrade"} <= functions, (
            f"{path.name} must define upgrade and downgrade"
        )


def test_alembic_configuration_points_at_the_migrations(repo: Path) -> None:
    ini = (repo / "alembic.ini").read_text()
    assert "script_location" in ini
    assert "migrations" in ini


def test_initial_revision_creates_the_core_tables(repo: Path) -> None:
    initial = repo / VERSIONS / "0001_initial.py"
    body = initial.read_text()
    for table in ("media_entities", "media_files", "download_tasks"):
        assert table in body, f"initial migration omits {table}"


@pytest.mark.parametrize(
    ("revision", "expected_table"),
    [
        ("0002_library_reports.py", "library_scan_reports"),
        ("0004_acquisition_approvals.py", "acquisition_approvals"),
        ("0005_wishlist_scheduling.py", "wishlist_items"),
        ("0006_agent_sessions.py", "agent_sessions"),
        ("0010_provider_platform_catalog.py", "provider_configs"),
    ],
)
def test_named_revision_creates_its_table(
    repo: Path, revision: str, expected_table: str
) -> None:
    body = (repo / VERSIONS / revision).read_text()
    assert expected_table in body or re.search(r"create_table\(", body), (
        f"{revision} does not appear to create {expected_table}"
    )
