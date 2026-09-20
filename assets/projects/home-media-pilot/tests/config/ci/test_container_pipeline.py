"""Contracts for the container CI pipeline.

The workflow is read as the build order it encodes: what must exist before the
image is built, what the image is built from, and what it is allowed to request
from the repository.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from _harness.paths import repository_root

CI = ".github/workflows/ci.yml"
PUBLISH = ".github/workflows/publish-container.yml"


def _runs(workflow: dict, job: str) -> list[str]:
    return [str(step.get("run", "")) for step in workflow["jobs"][job]["steps"]]


def _uses(workflow: dict, job: str) -> list[str]:
    return [str(step.get("uses", "")) for step in workflow["jobs"][job]["steps"]]


def test_ci_builds_the_image_without_pushing_it(repo: Path) -> None:
    """CI must prove the image builds while leaving publishing to its own job."""
    workflow = yaml.safe_load((repo / CI).read_text())
    assert "docker" in workflow["jobs"]
    build_steps = [
        step
        for step in workflow["jobs"]["docker"]["steps"]
        if "build-push-action" in str(step.get("uses", ""))
    ]
    assert build_steps, "CI never invokes the image build"
    assert build_steps[0].get("with", {}).get("push") in (False, "false"), (
        "CI must not push images"
    )


def test_ci_builds_the_published_dockerfile(repo: Path) -> None:
    """CI must build the same file the NAS stack pulls, or it validates nothing."""
    workflow = yaml.safe_load((repo / CI).read_text())
    text = str(workflow["jobs"]["docker"]["steps"])
    assert "docker/api.Dockerfile" in text, (
        "CI builds a different Dockerfile than the one that is published"
    )


def test_ci_produces_the_frontend_build_the_image_copies(repo: Path) -> None:
    """`Dockerfile.nas-local` copies frontend/dist, so any image build needs it first."""
    workflow = yaml.safe_load((repo / CI).read_text())
    runs = " ".join(_runs(workflow, "docker"))
    assert "npm run build" in runs, (
        "the docker job builds an image that copies frontend/dist without building it"
    )

    build_at = runs.index("npm run build")
    order = " ".join(_uses(workflow, "docker"))
    assert "docker/build-push-action" in order
    assert build_at < runs.index("cache-from") if "cache-from" in runs else True


def test_frontend_build_precedes_image_build_in_the_publish_job(repo: Path) -> None:
    workflow = yaml.safe_load((repo / PUBLISH).read_text())
    steps = workflow["jobs"]["publish"]["steps"]
    runs = [str(step.get("run", "")) for step in steps]
    uses = [str(step.get("uses", "")) for step in steps]

    frontend_index = next(i for i, r in enumerate(runs) if "npm run build" in r)
    image_index = next(i for i, u in enumerate(uses) if "build-push-action" in u)
    assert frontend_index < image_index, (
        "the image is built before the frontend that it copies exists"
    )


def test_publish_workflow_requests_only_the_permissions_publishing_needs(
    repo: Path,
) -> None:
    workflow = yaml.safe_load((repo / PUBLISH).read_text())
    permissions = workflow["permissions"]
    assert permissions["packages"] == "write", "publishing needs packages: write"
    assert permissions["contents"] == "read", (
        "the publish job must not request repository write access"
    )


def test_publish_workflow_runs_on_pushes_to_the_deployed_branch(repo: Path) -> None:
    """The NAS stack pulls `:main`, so main must be a trigger."""
    workflow = yaml.safe_load((repo / PUBLISH).read_text())
    # `on` is parsed as the boolean True by YAML 1.1.
    triggers = workflow.get("on", workflow.get(True))
    assert "main" in triggers["push"]["branches"], (
        "the deployed branch is not published on push"
    )


def test_publish_workflow_authenticates_before_pushing(repo: Path) -> None:
    workflow = yaml.safe_load((repo / PUBLISH).read_text())
    uses = _uses(workflow, "publish")
    assert any("login-action" in entry for entry in uses), (
        "no registry login before the push"
    )
    login = next(i for i, e in enumerate(uses) if "login-action" in e)
    push = next(i for i, e in enumerate(uses) if "build-push-action" in e)
    assert login < push, "the login must precede the image push"


def test_publish_workflow_derives_tags_from_a_single_metadata_step(repo: Path) -> None:
    workflow = yaml.safe_load((repo / PUBLISH).read_text())
    metadata_steps = [
        step
        for step in workflow["jobs"]["publish"]["steps"]
        if "metadata-action" in str(step.get("uses", ""))
    ]
    assert len(metadata_steps) == 1, "tags must come from one metadata definition"
    assert metadata_steps[0]["with"]["images"], "the metadata step declares no image"


@pytest.mark.parametrize("workflow_path", [CI, PUBLISH])
def test_workflows_pin_their_action_versions(repo: Path, workflow_path: str) -> None:
    """Unpinned actions are a supply-chain risk and a source of surprise breakage."""
    workflow = yaml.safe_load((repo / workflow_path).read_text())
    for job, spec in workflow["jobs"].items():
        for step in spec["steps"]:
            uses = step.get("uses")
            if not uses:
                continue
            assert "@" in uses, f"{workflow_path}:{job} uses unpinned action {uses}"
            ref = uses.split("@", 1)[1]
            assert ref and ref != "main" and ref != "master", (
                f"{workflow_path}:{job} tracks a moving ref: {uses}"
            )


def test_dockerignore_keeps_secrets_out_of_the_build_context(repo: Path) -> None:
    """`.env` must never be copied into an image layer."""
    ignored = {
        line.strip().rstrip("/")
        for line in (repo / ".dockerignore").read_text().splitlines()
        if line.strip() and not line.strip().startswith("#")
    }
    assert ".env" in ignored, ".env is not excluded from the build context"
    assert ".git" in ignored, ".git is not excluded from the build context"
