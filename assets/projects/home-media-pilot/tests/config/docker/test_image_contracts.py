"""Build contracts for the images: context resolution, pins, and entrypoints.

These assertions do not need a Docker daemon. They check the properties a build
depends on but cannot itself verify: that every declared `COPY` resolves inside
the declared build context, that the runtime the image starts is one the build
produces, and that the startup path runs migrations before serving.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from _harness.paths import repository_root

DOCKERFILES = {
    "docker/api.Dockerfile": {"context": ".", "dockerfile": "docker/api.Dockerfile"},
    "docker/Dockerfile.nas-local": {"context": ".", "dockerfile": "docker/Dockerfile.nas-local"},
}

COPY = re.compile(r"^COPY\s+(?P<srcs>.+?)\s+(?P<dest>\S+)\s*$")
IGNORED = re.compile(r"^([^\s!][^\s]*|[^\s!]+)$")


def _instructions(text: str) -> list[tuple[str, str]]:
    """Return (keyword, rest) for each non-comment instruction."""
    result = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        keyword, _, rest = stripped.partition(" ")
        result.append((keyword.upper(), rest.strip()))
    return result


def _build_artifacts(repo: Path) -> set[str]:
    """Paths a build step produces before the image is built.

    These are git-ignored by design and materialised by `npm run build`, which
    every build path runs first (`Makefile`, both workflows, and the NAS bundle
    script), so their absence from a clean checkout is expected rather than a
    broken `COPY`.
    """
    ignored: set[str] = set()
    for name in (".gitignore", ".dockerignore"):
        path = repo / name
        if not path.is_file():
            continue
        for line in path.read_text().splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and not stripped.startswith("!"):
                ignored.add(stripped.rstrip("/"))
    return ignored


@pytest.mark.parametrize("dockerfile", list(DOCKERFILES))
def test_every_copy_source_resolves_inside_the_build_context(
    repo: Path, dockerfile: str
) -> None:
    """A missing COPY source fails the build; catch it without building.

    Sources that a preceding build step produces are exempted when they are
    git-ignored, which is what marks them as generated rather than committed.
    """
    artifacts = _build_artifacts(repo)
    text = (repo / dockerfile).read_text()
    missing = []
    for keyword, rest in _instructions(text):
        if keyword != "COPY":
            continue
        match = COPY.match(f"COPY {rest}")
        assert match, f"unparsed COPY in {dockerfile}: {rest}"
        for source in match.group("srcs").split():
            if source.startswith("--"):
                continue
            if (repo / source).exists():
                continue
            if any(source == entry or source.startswith(f"{entry}/") for entry in artifacts):
                continue
            missing.append(source)
    assert missing == [], (
        f"{dockerfile} copies paths absent from the build context: {missing}"
    )


def test_generated_frontend_build_is_produced_before_every_image_build(
    repo: Path,
) -> None:
    """`docker/Dockerfile.nas-local` copies `src/frontend/dist`; it must exist first.

    Nothing in the Dockerfile builds the frontend, so the build depends on the
    caller having run `npm run build` against the same context.
    """
    text = (repo / "docker/Dockerfile.nas-local").read_text()
    assert "COPY src/frontend/dist" in text, "the NAS image no longer copies a built frontend"

    producers = {
        "Makefile": (repo / "Makefile").read_text(),
        ".github/workflows/ci.yml": (repo / ".github/workflows/ci.yml").read_text(),
        ".github/workflows/publish-container.yml": (
            repo / ".github/workflows/publish-container.yml"
        ).read_text(),
        "docker/create-nas-source-bundle.sh": (
            repo / "docker/create-nas-source-bundle.sh"
        ).read_text(),
    }
    for name, source in producers.items():
        assert "npm run build" in source or "npm ci" in source, (
            f"{name} builds an image path without producing frontend/dist"
        )


@pytest.mark.parametrize("dockerfile", list(DOCKERFILES))
def test_dockerfile_declares_a_base_and_a_start_command(
    repo: Path, dockerfile: str
) -> None:
    keywords = [keyword for keyword, _ in _instructions((repo / dockerfile).read_text())]
    assert "FROM" in keywords, f"{dockerfile} declares no base image"
    assert "CMD" in keywords or "ENTRYPOINT" in keywords, (
        f"{dockerfile} declares no start command"
    )


@pytest.mark.parametrize("dockerfile", list(DOCKERFILES))
def test_start_command_runs_a_venv_the_build_creates(
    repo: Path, dockerfile: str
) -> None:
    """The start command must reference the interpreter `uv sync` produces.

    A command pointing at a different venv path would fail at container start,
    which no static check of the Dockerfile alone would notice.
    """
    text = (repo / dockerfile).read_text()
    creates_venv = "uv sync" in text
    starts_venv = ".venv/" in text
    if starts_venv:
        assert creates_venv, (
            f"{dockerfile} starts .venv/... but never runs `uv sync` to create it"
        )


def test_published_image_installs_without_dev_dependencies(repo: Path) -> None:
    text = (repo / "docker/api.Dockerfile").read_text()
    assert "uv sync --frozen --no-dev" in text, (
        "the published image must exclude development dependencies"
    )


def test_published_image_pins_the_uv_version(repo: Path) -> None:
    text = (repo / "docker/api.Dockerfile").read_text()
    assert re.search(r"uv==\d+\.\d+\.\d+", text), "the uv version must be pinned"


def test_published_image_carries_the_migration_inputs(repo: Path) -> None:
    """Migrations are only runnable inside the image if their inputs are copied."""
    text = (repo / "docker/api.Dockerfile").read_text()
    assert "COPY src/migrations" in text
    assert "COPY alembic.ini" in text


def test_nas_local_image_runs_migrations_before_serving(repo: Path) -> None:
    """The NAS entrypoint must upgrade the schema before uvicorn starts.

    Ordering matters: serving against an un-migrated database would fail per
    request instead of once, at startup.
    """
    entrypoint = (repo / "docker/nas-entrypoint.sh").read_text()
    assert "alembic upgrade head" in entrypoint, "entrypoint never migrates"
    upgrade_at = entrypoint.index("alembic upgrade head")
    serve_at = entrypoint.index("uvicorn")
    assert upgrade_at < serve_at, "migrations must run before the server starts"


def test_nas_local_image_starts_via_its_entrypoint(repo: Path) -> None:
    text = (repo / "docker/Dockerfile.nas-local").read_text()
    assert "nas-entrypoint.sh" in text
    assert 'CMD ["/app/nas-entrypoint.sh"]' in text


def test_nas_local_image_ships_a_served_frontend_directory(repo: Path) -> None:
    """The WebUI routes need a built frontend at the directory the API serves."""
    text = (repo / "docker/Dockerfile.nas-local").read_text()
    assert "COPY src/frontend/dist ./frontend-dist" in text
    assert "ENV FRONTEND_DIST=/app/frontend-dist" in text


def test_published_image_wires_migrations_and_frontend(repo: Path) -> None:
    """Record the published image's actual shape.

    `docker/api.Dockerfile` follows the NAS image in copying the migration
    inputs, but unlike it declares no entrypoint that runs `alembic upgrade
    head`, and copies no built frontend while `apps/api/main.py` serves
    `FRONTEND_DIST` (default `/app/frontend-dist`). A container built from this
    file therefore serves against an un-migrated database and exposes no WebUI
    until a request triggers `create_all`.
    """
    text = (repo / "docker/api.Dockerfile").read_text()
    assert "alembic upgrade head" not in text, (
        "the published image now migrates; revisit this contract"
    )
    assert "nas-entrypoint.sh" not in text, (
        "the published image now uses an entrypoint; revisit this contract"
    )
    assert "frontend-dist" not in text, (
        "the published image now ships the frontend; revisit this contract"
    )
    assert "COPY frontend" not in text, (
        "the published image now copies frontend assets; revisit this contract"
    )


def test_dev_stack_services_start_without_migrating(repo: Path) -> None:
    """Record that no dev compose service runs a migration step.

    The API routes call `create_all` per request, which builds the schema from
    the models and so hides the absent migration step in development. Schema
    created that way can diverge from the migration chain.
    """
    compose = (repo / "docker-compose.yml").read_text()
    assert "alembic" not in compose, (
        "the dev stack now runs alembic; revisit this contract"
    )
