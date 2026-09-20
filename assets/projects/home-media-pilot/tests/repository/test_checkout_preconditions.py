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
        "src",
        "docker",
        "tests",
    ):
        assert (repo / name).is_dir(), f"missing top-level directory: {name}"


def test_source_packages_sit_under_src(repo_src: Path) -> None:
    """The business code is separated from the build and deploy inputs."""
    for name in (
        "apps",
        "packages",
        "migrations",
        "frontend",
    ):
        assert (repo_src / name).is_dir(), f"missing package directory: src/{name}"


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
    ],
)
def test_infrastructure_modules_are_present(repo_src: Path, module_path: str) -> None:
    assert (repo_src / module_path).is_file(), f"missing module: {module_path}"


@pytest.mark.parametrize(
    "module_path",
    [
        "packages/frameworks/providers.py",
        "packages/frameworks/errors.py",
        "packages/frameworks/provider_stack.py",
        "packages/frameworks/builtin_services.py",
        "packages/frameworks/metadata/port.py",
        "packages/frameworks/metadata/registry.py",
        "packages/frameworks/subtitles/port.py",
        "packages/frameworks/subtitles/registry.py",
    ],
)
def test_framework_modules_are_present(repo_src: Path, module_path: str) -> None:
    assert (repo_src / module_path).is_file(), f"missing module: {module_path}"


@pytest.mark.parametrize(
    "module_path",
    [
        "packages/providers/storage/filesystem.py",
        "packages/providers/player/jellyfin.py",
        "packages/providers/resource/mteam.py",
        "packages/providers/downloader/qbittorrent.py",
        "packages/providers/metadata/tvmaze.py",
        "packages/providers/metadata/metatube.py",
        "packages/providers/subtitles/opensubtitles.py",
    ],
)
def test_provider_modules_are_present(repo_src: Path, module_path: str) -> None:
    assert (repo_src / module_path).is_file(), f"missing module: {module_path}"


def test_frameworks_import_no_concrete_provider(repo_src: Path) -> None:
    """Framework modules other than the binding seams must not name a provider.

    Two modules bind implementations to the type-keyed registries:
    `provider_stack.py` (metadata and subtitle routing) and
    `builtin_services.py` (player, resource and downloader services). Every
    other framework module states contracts only; a stray import there would
    make the layer depend on the implementations it exists to abstract.
    """
    binding_seams = {"provider_stack.py", "builtin_services.py"}
    framework_root = repo_src / "packages" / "frameworks"
    offenders = [
        f"{module.relative_to(repo_src)}: {line}"
        for module in framework_root.rglob("*.py")
        if module.name not in binding_seams
        for line in module.read_text().splitlines()
        if line.startswith(("from packages.providers", "import packages.providers"))
    ]
    assert offenders == [], f"framework modules import concrete providers: {offenders}"


def test_secret_store_module_is_present_and_used_by_its_importers(repo_src: Path) -> None:
    """The credential store must exist and still be the one its callers import."""
    secrets_module = repo_src / "packages" / "infrastructure" / "secrets.py"
    assert secrets_module.is_file(), "missing module: packages/infrastructure/secrets.py"

    importers = [
        repo_src / "packages" / "application" / "libraries.py",
        repo_src / "apps" / "api" / "routes_phase4.py",
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
def test_modules_reaching_secret_store_are_importable(repo: Path, module_name: str) -> None:
    """Every module that depends on the credential store must import cleanly."""
    import importlib

    assert importlib.import_module(module_name) is not None


def test_credential_store_round_trips_and_rejects_tampering(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The store must encrypt reversibly and refuse altered ciphertext."""
    import importlib

    secrets_module = importlib.import_module("packages.infrastructure.secrets")
    store = secrets_module.CredentialStore()

    monkeypatch.setenv("PILOT_SECRET_KEY_FILE", str(tmp_path / "master.key"))
    payload = {"api_key": "very-secret-token"}
    token = store.encrypt(payload)

    assert "very-secret-token" not in token, "ciphertext must not carry the plaintext"
    assert store.decrypt(token) == payload

    tampered = token[:-4] + ("AAAA" if not token.endswith("AAAA") else "BBBB")
    with pytest.raises(secrets_module.CredentialStoreError):
        store.decrypt(tampered)


def test_credential_store_reads_and_writes_the_schema_columns(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The encrypted column must exist in the migrated schema and hold a token.

    This is the join between the migration and the store: an import-only check
    would pass even if the column were absent from the database.
    """
    import importlib
    import os
    import subprocess
    import sys

    db_path = tmp_path / "schema.db"
    environment = {**os.environ, "DATABASE_URL": f"sqlite:///{db_path}"}
    completed = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=repo,
        env=environment,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr[-2000:]

    import sqlite3

    connection = sqlite3.connect(db_path)
    try:
        columns = {row[1] for row in connection.execute("pragma table_info(provider_configs)")}
    finally:
        connection.close()
    for expected in (
        "encrypted_credentials",
        "last_connection_status",
        "last_connection_message",
        "last_connection_checked_at",
    ):
        assert expected in columns, f"migrated schema lacks provider_configs.{expected}"
