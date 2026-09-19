"""Mirrors `apps/cli`: the command surface and its policy behaviour.

The CLI entry point assembles every command group, and that assembly reaches the
absent secret store. Rather than duplicate the gate, the structural checks read
the source; behaviour checks run only when the CLI imports.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

import typer

from _harness.paths import repository_root

CLI_DIR = "apps/cli"


def test_every_cli_module_is_present(repo: Path) -> None:
    modules = repo / CLI_DIR
    for name in (
        "main.py",
        "library.py",
        "services.py",
        "providers.py",
        "acquisition.py",
        "agent.py",
        "automation.py",
        "wishlist.py",
        "jellyfin.py",
        "operations.py",
    ):
        assert (modules / name).is_file(), f"missing CLI module: {name}"


def test_command_groups_are_registered_on_the_root_app(repo: Path) -> None:
    source = (repo / CLI_DIR / "main.py").read_text()
    groups = set(re.findall(r'app\.add_typer\(\w+, name="([a-z-]+)"\)', source))
    assert groups == {
        "system",
        "library",
        "jellyfin",
        "metadata",
        "subtitles",
        "services",
        "acquisition",
        "wishlist",
        "schedule",
        "release",
        "download",
        "job",
        "config",
        "agent",
        "automation",
    }


def _cli_or_fail():
    """Load the CLI, turning a blocked import into an explicit failure."""
    import importlib

    try:
        return importlib.import_module("apps.cli.main").app
    except ModuleNotFoundError as exc:
        assert "packages.infrastructure.secrets" not in str(exc), (
            "the CLI cannot be assembled: apps.cli.main reaches the absent "
            "module packages.infrastructure.secrets. Restore it to pass."
        )
        raise


def test_doctor_reports_service_identity_in_json(capsys: pytest.CaptureFixture[str]) -> None:
    app = _cli_or_fail()
    runner = typer.testing.CliRunner()
    result = runner.invoke(app, ["system", "doctor", "--output", "json"])
    assert result.exit_code == 0
    assert "home-media-pilot" in result.stdout


def test_doctor_rejects_an_unknown_output_format() -> None:
    app = _cli_or_fail()
    runner = typer.testing.CliRunner()
    result = runner.invoke(app, ["system", "doctor", "--output", "yaml"])
    assert result.exit_code != 0


def test_root_app_requires_a_subcommand() -> None:
    app = _cli_or_fail()
    runner = typer.testing.CliRunner()
    result = runner.invoke(app, [])
    assert result.exit_code != 0
