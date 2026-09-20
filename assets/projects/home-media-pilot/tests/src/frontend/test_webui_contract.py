"""Mirrors `frontend/`: WebUI source, its API coupling, and build inputs."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from _harness.paths import repository_root

FRONTEND = "src/frontend"


def test_frontend_entry_files_are_present(repo: Path) -> None:
    for name in (
        "index.html",
        "package.json",
        "tsconfig.json",
        "vite.config.ts",
        "src/main.tsx",
    ):
        assert (repo / FRONTEND / name).is_file(), f"missing frontend file: {name}"


def test_main_tsx_renders_into_the_index_mount_point(repo: Path) -> None:
    main = (repo / FRONTEND / "src/main.tsx").read_text()
    index = (repo / FRONTEND / "index.html").read_text()
    mount_ids = set(re.findall(r'getElementById\("([^"]+)"\)', main))
    assert mount_ids, "main.tsx does not mount into a DOM element"
    for mount_id in mount_ids:
        assert f'id="{mount_id}"' in index, f"index.html lacks mount point {mount_id}"


def test_bundler_output_directory_is_not_wired_to_the_served_directory(
    repo: Path,
) -> None:
    """Record the current build wiring.

    `apps/api/main.py` serves `FRONTEND_DIST`, defaulting to `/app/frontend-dist`.
    The Vite config sets no `outDir` (so it emits `frontend/dist`), and
    `docker/api.Dockerfile` neither copies a built frontend nor sets
    `FRONTEND_DIST`. Nothing therefore populates the served directory in the
    container, and the WebUI routes are unreachable there. This test pins that
    state; wiring the two together makes it fail.
    """
    config = (repo / FRONTEND / "vite.config.ts").read_text()
    api_main = (repo / "src/apps/api/main.py").read_text()
    dockerfile = (repo / "docker/api.Dockerfile").read_text()

    assert "outDir" not in config, "vite now sets outDir; revisit this wiring test"
    assert 'FRONTEND_DIST", "/app/frontend-dist"' in api_main
    assert "frontend-dist" not in dockerfile, (
        "the API image now ships the frontend; revisit this wiring test"
    )
    assert "COPY frontend" not in dockerfile, (
        "the API image now copies frontend sources; revisit this wiring test"
    )


def test_api_base_url_is_configurable_for_split_deployment(repo: Path) -> None:
    """NAS deploys serve the WebUI and API from different origins."""
    main = (repo / FRONTEND / "src/main.tsx").read_text()
    assert "VITE_API_BASE_URL" in main, (
        "the WebUI must accept a configurable API origin"
    )


def test_webui_calls_every_flow_route_it_presents(repo: Path) -> None:
    main = (repo / FRONTEND / "src/main.tsx").read_text()
    for route in (
        "/media-libraries",
        "/media-libraries/",
        "/library/status",
        "/services/status",
        "/services/qb/health",
        "/services/qb/tasks",
        "/services/mteam/search",
    ):
        assert route in main, f"the WebUI never calls {route}"


def test_frontend_performs_no_filesystem_or_server_side_mutation(repo: Path) -> None:
    """The WebUI is a client: it must not embed shell or file operations."""
    main = (repo / FRONTEND / "src/main.tsx").read_text()
    for forbidden in ("require(", "child_process", "fs.writeFile", "exec("):
        assert forbidden not in main, f"WebUI source contains {forbidden}"


def test_typescript_is_configured_strictly(repo: Path) -> None:
    config = json.loads(_strip_jsonc((repo / FRONTEND / "tsconfig.json").read_text()))
    compiler = config.get("compilerOptions", {})
    assert compiler.get("strict") is True, "TypeScript strict mode must stay on"


def test_api_base_defaults_to_relative_same_origin(repo: Path) -> None:
    """Without an explicit origin the client must fall back to same-origin calls."""
    main = (repo / FRONTEND / "src/main.tsx").read_text()
    assert 'import.meta.env.VITE_API_BASE_URL ?? ""' in main or (
        'import.meta.env.VITE_API_BASE_URL || ""' in main
    ), "the API base must default to an empty (same-origin) prefix"


def _strip_jsonc(text: str) -> str:
    """Remove // and /* */ comments and trailing commas so json can parse."""
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    text = re.sub(r"(^|[^:])//.*$", r"\1", text, flags=re.M)
    text = re.sub(r",(\s*[}\]])", r"\1", text)
    return text


def test_frontend_declares_react_and_a_bundler(repo: Path) -> None:
    package = json.loads((repo / FRONTEND / "package.json").read_text())
    declared = {**package.get("dependencies", {}), **package.get("devDependencies", {})}
    assert "react" in declared
    assert "react-dom" in declared
    assert "vite" in declared


def test_lockfile_is_committed_for_reproducible_installs(repo: Path) -> None:
    assert (repo / FRONTEND / "package-lock.json").is_file()


def test_frontend_has_no_test_runner_declared(repo: Path) -> None:
    """Record the current shape: the WebUI ships build-only CI, no unit runner.

    Adding a frontend test runner makes this fail, which is the intended signal
    that this suite's coverage statement needs revisiting.
    """
    package = json.loads((repo / FRONTEND / "package.json").read_text())
    declared = {**package.get("dependencies", {}), **package.get("devDependencies", {})}
    runners = {"vitest", "jest", "@testing-library/react", "playwright"}
    assert not (runners & set(declared)), (
        f"a frontend test runner is now declared: {runners & set(declared)}"
    )
    assert "test" not in package["scripts"]


@pytest.mark.parametrize("name", ["style.css", "settings-session.css", "confirm-session.css"])
def test_stylesheets_are_present(repo: Path, name: str) -> None:
    assert (repo / FRONTEND / "src" / name).is_file()
