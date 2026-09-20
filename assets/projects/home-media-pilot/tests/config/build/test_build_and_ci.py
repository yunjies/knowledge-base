"""Mirrors the build and CI configuration: Makefile, pyproject, workflows."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

from _harness.paths import repository_root

import yaml


def test_makefile_exposes_the_expected_targets(repo: Path) -> None:
    targets = set(re.findall(r"^([a-z-]+):", (repo / "Makefile").read_text(), re.M))
    assert targets >= {
        "install",
        "test",
        "lint",
        "format",
        "frontend-build",
        "check",
    }


def test_makefile_check_aggregates_the_gates(repo: Path) -> None:
    text = (repo / "Makefile").read_text()
    check_line = next(line for line in text.splitlines() if line.startswith("check:"))
    for gate in ("test", "lint", "frontend-build"):
        assert gate in check_line, f"check does not run {gate}"


def test_pyproject_declares_the_runtime_and_dev_dependencies(repo: Path) -> None:
    project = tomllib.loads((repo / "pyproject.toml").read_text())["project"]
    dependencies = " ".join(project["dependencies"])
    for package in ("fastapi", "pydantic", "sqlalchemy", "alembic", "httpx", "typer"):
        assert package in dependencies, f"missing runtime dependency: {package}"


def test_pyproject_points_pytest_at_a_test_directory(repo: Path) -> None:
    config = tomllib.loads((repo / "pyproject.toml").read_text())
    assert config["tool"]["pytest"]["ini_options"]["testpaths"]


def test_pyproject_console_script_points_at_the_cli(repo: Path) -> None:
    scripts = tomllib.loads((repo / "pyproject.toml").read_text())["project"]["scripts"]
    assert scripts["media-pilot"] == "apps.cli.main:app"


def test_lint_selects_the_documented_rule_families(repo: Path) -> None:
    ruff = tomllib.loads((repo / "pyproject.toml").read_text())["tool"]["ruff"]["lint"]
    assert set(ruff["select"]) >= {"E", "F", "I", "UP", "B"}


def test_ci_runs_every_documented_gate(repo: Path) -> None:
    workflow = yaml.safe_load((repo / ".github/workflows/ci.yml").read_text())
    jobs = workflow["jobs"]
    assert set(jobs) >= {"backend", "frontend", "docker"}

    backend_steps = " ".join(
        str(step.get("run", "")) for step in jobs["backend"]["steps"]
    )
    assert "pytest" in backend_steps
    assert "ruff check" in backend_steps


def test_ci_pins_the_toolchain_versions(repo: Path) -> None:
    text = (repo / ".github/workflows/ci.yml").read_text()
    assert "python-version" in text
    assert "node-version" in text
    assert "uv" in text


def test_container_publish_workflow_pushes_to_ghcr(repo: Path) -> None:
    workflow = yaml.safe_load(
        (repo / ".github/workflows/publish-container.yml").read_text()
    )
    assert "ghcr.io" in str(workflow)
    assert workflow["permissions"]["packages"] == "write", (
        "publishing an image requires packages: write"
    )
    assert workflow["permissions"]["contents"] == "read", (
        "the publish job must not request repository write access"
    )


def test_frontend_package_declares_build_and_dev_scripts(repo: Path) -> None:
    import json

    package = json.loads((repo / "src/frontend/package.json").read_text())
    assert {"dev", "build"} <= set(package["scripts"])
    assert "vite" in package["devDependencies"] or "vite" in package["dependencies"]


def test_frontend_build_typechecks_before_bundling(repo: Path) -> None:
    import json

    package = json.loads((repo / "src/frontend/package.json").read_text())
    assert "tsc" in package["scripts"]["build"], "build must typecheck before bundling"
