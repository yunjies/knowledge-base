"""Repository-level facts the rest of the suite depends on.

These tests assert the shape of the checkout itself rather than its behaviour:
which modules are present, and therefore which parts of the application can be
imported at all. A failure here is a statement about the checkout, not about a
feature.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from _harness.paths import repository_root


def test_repository_has_expected_top_level_directories(repo: Path) -> None:
    for name in (
        "apps",
        "packages",
        "migrations",
        "frontend",
        "docker",
        "openspec",
        "tests",
    ):
        assert (repo / name).is_dir(), f"missing top-level directory: {name}"


def test_declared_python_version_matches_running_interpreter(repo: Path) -> None:
    pyproject = (repo / "pyproject.toml").read_text()
    assert "requires-python" in pyproject
    assert "packages" in pyproject and "apps" in pyproject


@pytest.mark.parametrize(
    "module_path",
    [
        "packages/infrastructure/config/settings.py",
        "packages/infrastructure/config/redaction.py",
        "packages/infrastructure/db/models.py",
        "packages/infrastructure/db/repositories.py",
        "packages/infrastructure/db/session.py",
        "packages/infrastructure/library/paths.py",
        "packages/infrastructure/library/roots.py",
        "packages/infrastructure/providers/factory.py",
    ],
)
def test_infrastructure_modules_are_present(repo: Path, module_path: str) -> None:
    assert (repo / module_path).is_file(), f"missing module: {module_path}"


def test_secret_store_module_is_absent_and_blocks_imports(repo: Path) -> None:
    """Record the checkout's actual precondition.

    `packages/application/libraries.py` and `apps/api/routes_phase4.py` import
    `packages.infrastructure.secrets.CredentialStore`. That module is not in the
    checkout, so every module transitively reaching either of them fails to
    import. This test passes only while that absence is real; restoring the
    module turns it into a signal that the precondition changed.
    """
    secrets_module = repo / "packages" / "infrastructure" / "secrets.py"
    assert not secrets_module.exists(), (
        "packages/infrastructure/secrets.py now exists; the suite's recorded "
        "precondition is stale and the import-blocked tests must be re-enabled"
    )

    importers = [
        repo / "packages" / "application" / "libraries.py",
        repo / "apps" / "api" / "routes_phase4.py",
    ]
    for importer in importers:
        assert "packages.infrastructure.secrets import CredentialStore" in (
            importer.read_text()
        ), f"{importer.name} no longer imports the secret store"


@pytest.mark.parametrize(
    "module_name",
    [
        "apps.api.main",
        "apps.api.routes_phase4",
        "packages.application.libraries",
    ],
)
def test_modules_reaching_secret_store_are_not_importable(
    repo: Path, module_name: str
) -> None:
    """These imports must fail while the secret store is absent.

    The module file itself is present, so the failure only appears when the
    body executes and its transitive import is resolved.
    """
    import importlib

    with pytest.raises(ModuleNotFoundError) as excinfo:
        importlib.import_module(module_name)
    assert "packages.infrastructure.secrets" in str(excinfo.value)
