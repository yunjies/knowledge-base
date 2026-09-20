"""Mirrors `packages/adapters`: error contract and read-only filesystem probing."""

from __future__ import annotations

from pathlib import Path

import pytest

from packages.adapters.errors import ProviderError
from packages.adapters.filesystem import FilesystemLandingReadOnlyAdapter
from packages.domain.states import ErrorCategory


def test_provider_error_carries_provider_and_category() -> None:
    error = ProviderError("qbittorrent", ErrorCategory.TIMEOUT, "timed out")
    assert error.provider_id == "qbittorrent"
    assert error.category is ErrorCategory.TIMEOUT
    assert error.status_code is None
    assert str(error) == "timed out"


def test_provider_error_records_upstream_status_code() -> None:
    error = ProviderError(
        "jellyfin", ErrorCategory.AUTHENTICATION, "denied", status_code=401
    )
    assert error.status_code == 401


def test_filesystem_adapter_reports_missing_path_without_writing(
    tmp_path: Path,
) -> None:
    target = tmp_path / "absent"
    result = FilesystemLandingReadOnlyAdapter().inspect(str(target))
    assert result["exists"] is False
    assert result["entry_count"] == 0
    assert not target.exists(), "probing must not create the path"


def test_filesystem_adapter_counts_entries_in_a_directory(tmp_path: Path) -> None:
    landing = tmp_path / "downloads" / "Dune"
    landing.mkdir(parents=True)
    (landing / "a.mkv").write_bytes(b"x")
    (landing / "b.srt").write_text("1\n")

    result = FilesystemLandingReadOnlyAdapter().inspect(str(landing))
    assert result["exists"] is True
    assert result["is_directory"] is True
    assert result["entry_count"] == 2


def test_filesystem_adapter_flags_a_non_directory(tmp_path: Path) -> None:
    target = tmp_path / "file.mkv"
    target.write_bytes(b"media")
    result = FilesystemLandingReadOnlyAdapter().inspect(str(target))
    assert result["exists"] is True
    assert result["is_directory"] is False


@pytest.mark.parametrize(
    "adapter_module",
    [
        "packages.adapters.qbittorrent",
        "packages.adapters.mteam",
        "packages.adapters.jellyfin",
    ],
)
def test_read_only_adapters_expose_no_mutation_methods(adapter_module: str) -> None:
    """Read-only adapters must not offer add/delete/move style entry points."""
    import importlib
    import inspect

    module = importlib.import_module(adapter_module)
    forbidden = ("add", "delete", "remove", "move", "rename", "refresh", "scan")
    for _name, cls in inspect.getmembers(module, inspect.isclass):
        if cls.__module__ != module.__name__:
            continue
        public = [m for m in dir(cls) if not m.startswith("_")]
        offenders = [
            method
            for method in public
            if any(method == word or method.startswith(f"{word}_") for word in forbidden)
        ]
        assert not offenders, f"{cls.__name__} exposes mutation methods: {offenders}"
