"""Runtime contracts for the Compose stacks: wiring, isolation, and data safety.

Each assertion answers a question an operator would ask before deploying: does
the image the file references exist, do the services that need a database wait
for one, is media ever mounted writable, and does state outlive the container.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from _harness.paths import repository_root

STACKS = {
    "docker-compose.yml": "development",
    "docker-compose.nas.yml": "published image to a NAS",
}


def _compose(repo: Path, name: str) -> dict:
    return yaml.safe_load((repo / name).read_text())


@pytest.mark.parametrize("name", list(STACKS))
def test_stack_references_only_local_dockerfiles_or_remote_images(
    repo: Path, name: str
) -> None:
    """A build must name a Dockerfile that exists; an image must be fully qualified."""
    services = _compose(repo, name)["services"]
    for service, spec in services.items():
        build = spec.get("build")
        image = spec.get("image")
        if isinstance(build, str):
            assert (repo / build).is_file(), f"{name}:{service} builds missing {build}"
        elif isinstance(build, dict):
            dockerfile = build.get("dockerfile")
            assert dockerfile, f"{name}:{service} declares a build without a dockerfile"
            assert (repo / dockerfile).is_file(), (
                f"{name}:{service} builds missing {dockerfile}"
            )
        elif build is None:
            assert image, f"{name}:{service} has neither build nor image"
        if image and "/" not in image:
            assert image in {"postgres:16-alpine", "node:22-alpine"}, (
                f"{name}:{service} uses an unexpected short image reference: {image}"
            )


def test_every_published_image_reference_matches_the_publish_workflow(
    repo: Path,
) -> None:
    """The NAS stack pulls an image; CI must publish that repository name.

    The workflow interpolates the owner (`${{ github.repository_owner }}`), so
    only the repository component can be compared literally.
    """
    nas = _compose(repo, "docker-compose.nas.yml")["services"]
    referenced = {spec["image"] for spec in nas.values() if spec.get("image")}
    assert referenced, "the NAS stack pulls no image"
    workflow = (repo / ".github/workflows/publish-container.yml").read_text()
    for image in referenced:
        repository = image.split(":")[0]
        owner, _, name = repository.rpartition("/")
        assert owner.startswith("ghcr.io/"), f"{image} is not a GHCR reference"
        assert "registry: ghcr.io" in workflow, "the workflow pushes to no registry"
        assert name in workflow, (
            f"{image} is pulled by the NAS stack but the workflow publishes "
            f"no image named {name}"
        )


def test_api_port_mapping_targets_the_port_the_image_exposes(repo: Path) -> None:
    """A mismatch here silently publishes nothing.

    Only services built from the API image are checked; the development frontend
    runs Vite on its own port.
    """
    for name in STACKS:
        services = _compose(repo, name)["services"]
        for service, spec in services.items():
            build = spec.get("build")
            if not build:
                continue
            dockerfile = build if isinstance(build, str) else build.get("dockerfile", "")
            if "api.Dockerfile" not in dockerfile and "Dockerfile.nas" not in dockerfile:
                continue
            for mapping in spec.get("ports", []) or []:
                _host, _, container = str(mapping).partition(":")
                assert container == "8000", (
                    f"{name}:{service} maps to container port {container}, "
                    "but the image exposes 8000"
                )


def test_services_sharing_an_image_share_a_build_definition(repo: Path) -> None:
    """The API, worker, and scheduler must run the same code.

    If their build definitions diverged, a task would execute against a
    different revision than the one that enqueued it.
    """
    services = _compose(repo, "docker-compose.yml")["services"]
    shared = ["api", "worker", "scheduler"]
    builds = {service: services[service]["build"]["dockerfile"] for service in shared}
    assert len(set(builds.values())) == 1, f"divergent builds across {builds}"


def test_services_reaching_the_database_wait_for_it_to_be_healthy(repo: Path) -> None:
    services = _compose(repo, "docker-compose.yml")["services"]
    for service in ("api", "worker", "scheduler"):
        depends = services[service].get("depends_on", {})
        assert depends, f"{service} does not declare a dependency on the database"
        assert depends["db"]["condition"] == "service_healthy", (
            f"{service} does not wait for a healthy database"
        )


@pytest.mark.parametrize(
    "name", ["docker-compose.nas.yml"]
)
def test_media_and_download_mounts_are_read_only(repo: Path, name: str) -> None:
    """Pilot must never hold a writable handle on the media it indexes."""
    services = _compose(repo, name)["services"]
    mounts = [
        str(volume)
        for spec in services.values()
        for volume in spec.get("volumes", []) or []
    ]
    protected = [m for m in mounts if "/media" in m or "/downloads" in m]
    assert protected, f"{name} mounts neither a media nor a download root"
    for mount in protected:
        assert mount.endswith(":ro"), f"writable media mount in {name}: {mount}"


def test_stateful_services_declare_named_volumes(repo: Path) -> None:
    """Application state must survive a container replacement."""
    compose = _compose(repo, "docker-compose.yml")
    declared = set(compose.get("volumes") or {})
    used = {
        str(volume).split(":")[0]
        for spec in compose["services"].values()
        for volume in spec.get("volumes", []) or []
        if not str(volume).startswith((".", "/", "~"))
    }
    missing = used - declared
    assert missing == set(), f"volumes mounted but not declared: {sorted(missing)}"


def test_environment_values_are_strings_or_empty(repo: Path) -> None:
    """YAML would coerce bare numbers/booleans into non-string env values."""
    for name in STACKS:
        services = _compose(repo, name)["services"]
        for service, spec in services.items():
            environment = spec.get("environment")
            if environment is None or isinstance(environment, list):
                continue
            for key, value in environment.items():
                assert value is None or isinstance(value, str), (
                    f"{name}:{service}.{key} is {type(value).__name__}, not a string"
                )


def test_nas_stack_requires_its_mount_sources_to_be_set(repo: Path) -> None:
    """Unset media roots must fail the deploy rather than mount an empty path."""
    text = (repo / "docker-compose.nas.yml").read_text()
    assert "${MEDIA_ROOT:?" in text or "${MEDIA_ROOT?" in text
    assert "${DOWNLOADS_ROOT:?" in text or "${DOWNLOADS_ROOT?" in text


def test_nas_stack_injects_configuration_rather_than_committing_it(repo: Path) -> None:
    """Secrets and endpoints are injected at deploy time, never committed."""
    services = _compose(repo, "docker-compose.nas.yml")["services"]
    env_files = services["api"].get("env_file")
    assert env_files, "the NAS stack declares no env_file"
    assert ".env" in [str(entry) for entry in env_files]
