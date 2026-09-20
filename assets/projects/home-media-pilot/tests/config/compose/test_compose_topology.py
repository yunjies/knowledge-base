"""Mirrors the deployment configuration: compose files, Dockerfiles, entrypoints."""

from __future__ import annotations

from pathlib import Path

import pytest

from _harness.paths import repository_root

import yaml

COMPOSE_FILES = [
    "docker-compose.yml",
    "docker-compose.nas.yml",
    "docker-compose.nas-local.yml",
    "docker-compose.unraid.yml",
]


@pytest.mark.parametrize("name", COMPOSE_FILES)
def test_compose_file_is_valid_yaml_with_services(repo: Path, name: str) -> None:
    document = yaml.safe_load((repo / name).read_text())
    assert isinstance(document, dict)
    assert document.get("services"), f"{name} declares no services"


def test_development_compose_runs_the_full_process_set(repo: Path) -> None:
    services = yaml.safe_load((repo / "docker-compose.yml").read_text())["services"]
    assert set(services) >= {"db", "api", "worker", "scheduler"}
    assert services["worker"]["command"] == ["python", "-m", "apps.worker"]
    assert services["scheduler"]["command"] == ["python", "-m", "apps.scheduler"]


def test_development_database_is_postgres_with_a_healthcheck(repo: Path) -> None:
    db = yaml.safe_load((repo / "docker-compose.yml").read_text())["services"]["db"]
    assert "postgres" in db["image"]
    assert "healthcheck" in db


def test_api_depends_on_a_healthy_database(repo: Path) -> None:
    api = yaml.safe_load((repo / "docker-compose.yml").read_text())["services"]["api"]
    assert api["depends_on"]["db"]["condition"] == "service_healthy"


def test_application_services_poll_the_health_route(repo: Path) -> None:
    """Services built from the API image must gate on the app's own /health route.

    The database is excluded: it is gated by its own engine-level probe.
    """
    compose = yaml.safe_load((repo / "docker-compose.yml").read_text())
    for name in ("api",):
        command = " ".join(compose["services"][name]["healthcheck"]["test"])
        assert "/health" in command, f"{name} healthcheck does not poll /health"

    db_command = " ".join(compose["services"]["db"]["healthcheck"]["test"])
    assert "pg_isready" in db_command, "db must be gated by pg_isready"


@pytest.mark.parametrize("name", ["docker-compose.nas.yml", "docker-compose.nas-local.yml"])
def test_nas_compose_mounts_media_read_only(repo: Path, name: str) -> None:
    """NAS deployments must never mount the media or download roots writable."""
    services = yaml.safe_load((repo / name).read_text())["services"]
    volumes = [v for service in services.values() for v in service.get("volumes", [])]
    media_mounts = [v for v in volumes if "/media" in v or "/downloads" in v]
    assert media_mounts, f"{name} mounts no media or download root"
    for mount in media_mounts:
        assert str(mount).endswith(":ro"), f"writable media mount in {name}: {mount}"


def test_nas_local_compose_declares_read_only_environment(repo: Path) -> None:
    environment = yaml.safe_load((repo / "docker-compose.nas-local.yml").read_text())[
        "services"
    ]["api"]["environment"]
    assert environment["MEDIA_READ_ONLY"] == "true"
    assert environment["DOWNLOADS_READ_ONLY"] == "true"
    assert environment["DATABASE_URL"].startswith("sqlite:")


def test_nas_local_compose_declares_an_unraid_webui_label(repo: Path) -> None:
    labels = yaml.safe_load((repo / "docker-compose.nas-local.yml").read_text())[
        "services"
    ]["api"]["labels"]
    assert "net.unraid.docker.webui" in labels


def test_dockerfiles_are_present_and_use_a_python_base(repo: Path) -> None:
    for name in ("docker/api.Dockerfile", "docker/Dockerfile.nas-local"):
        text = (repo / name).read_text()
        assert "FROM" in text and "python" in text.lower(), f"{name} lacks a python base"


def test_api_dockerfile_exposes_the_service_port(repo: Path) -> None:
    text = (repo / "docker/api.Dockerfile").read_text()
    assert "EXPOSE 8000" in text


def test_nas_entrypoint_and_bundle_scripts_exist(repo: Path) -> None:
    for name in ("docker/nas-entrypoint.sh", "docker/create-nas-source-bundle.sh"):
        assert (repo / name).is_file(), f"missing script: {name}"


SECRET_KEYS = ("KEY", "TOKEN", "PASSWORD", "SECRET", "CREDENTIAL")


def test_env_example_commits_no_real_secret_value(repo: Path) -> None:
    """Keys that name a secret must be blank or an obvious placeholder."""
    placeholders = {"", "changeme", "replace-me", "your-key-here"}
    text = (repo / ".env.example").read_text()
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _sep, value = stripped.partition("=")
        if any(marker in key.upper() for marker in SECRET_KEYS):
            assert value in placeholders, f"possible real secret in .env.example: {key}"
