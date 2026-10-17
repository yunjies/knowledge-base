"""The main branch keeps no project-specific material."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from _harness import paths


def project_tree_errors(root: Path) -> list[str]:
    """Require a tracked empty-directory marker and no project entries."""
    if root.is_symlink() or not root.is_dir():
        return ["assets/projects must exist as a regular directory"]
    entries = list(root.iterdir())
    errors = []
    unexpected = sorted(entry.name for entry in entries if entry.name != ".gitkeep")
    if unexpected:
        errors.append(f"project-specific entries are forbidden: {unexpected}")
    marker = root / ".gitkeep"
    if not marker.is_file() or marker.is_symlink():
        errors.append("assets/projects must contain a regular .gitkeep file")
    elif marker.stat().st_size != 0:
        errors.append("assets/projects/.gitkeep must be empty")
    return errors


def tracked_project_paths(repository_root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "-C", str(repository_root), "ls-files", "--", "assets/projects"],
        check=True,
        capture_output=True,
        text=True,
    )
    return sorted(result.stdout.splitlines())


def is_main_guard_context() -> bool:
    """Identify main in GitHub's detached checkout and in local attached checkouts.

    The workflow runs only for pushes to main and pull requests; Actions supplies
    GITHUB_REF for pushes and GITHUB_BASE_REF for pull requests independently of
    whether checkout has attached a local branch.
    """
    event = os.environ.get("GITHUB_EVENT_NAME")
    if event == "push":
        return os.environ.get("GITHUB_REF") == "refs/heads/main"
    if event == "pull_request":
        return os.environ.get("GITHUB_BASE_REF") == "main"
    if event is not None:
        raise AssertionError(f"cannot determine main applicability for GitHub event {event!r}")
    result = subprocess.run(
        ["git", "-C", str(paths.repository_root()), "branch", "--show-current"],
        check=True,
        capture_output=True,
        text=True,
    )
    branch = result.stdout.strip()
    if not branch:
        raise AssertionError("detached checkout has no GitHub branch context for main applicability")
    return branch == "main"


@pytest.mark.parametrize(
    ("event", "environment", "expected"),
    [
        ("push", {"GITHUB_REF": "refs/heads/main"}, True),
        ("push", {"GITHUB_REF": "refs/heads/duoduo"}, False),
        ("pull_request", {"GITHUB_BASE_REF": "main"}, True),
        ("pull_request", {"GITHUB_BASE_REF": "duoduo"}, False),
    ],
)
def test_github_main_guard_context(monkeypatch, event, environment, expected) -> None:
    monkeypatch.setenv("GITHUB_EVENT_NAME", event)
    monkeypatch.delenv("GITHUB_REF", raising=False)
    monkeypatch.delenv("GITHUB_BASE_REF", raising=False)
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    assert is_main_guard_context() is expected


def test_unknown_github_event_fails_loud(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_EVENT_NAME", "workflow_dispatch")
    with pytest.raises(AssertionError, match="cannot determine main applicability"):
        is_main_guard_context()


def test_local_attached_main_is_guarded(monkeypatch) -> None:
    monkeypatch.delenv("GITHUB_EVENT_NAME", raising=False)
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, stdout="main\n", stderr=""),
    )
    assert is_main_guard_context() is True


def test_local_attached_duoduo_is_not_guarded(monkeypatch) -> None:
    monkeypatch.delenv("GITHUB_EVENT_NAME", raising=False)
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, stdout="duoduo\n", stderr=""),
    )
    assert is_main_guard_context() is False


def test_detached_local_checkout_fails_loud(monkeypatch) -> None:
    monkeypatch.delenv("GITHUB_EVENT_NAME", raising=False)
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, stdout="\n", stderr=""),
    )
    with pytest.raises(AssertionError, match="detached checkout"):
        is_main_guard_context()


def test_push_to_main_enforces_directory_check_in_detached_actions_checkout(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("GITHUB_EVENT_NAME", "push")
    monkeypatch.setenv("GITHUB_REF", "refs/heads/main")
    monkeypatch.setattr(paths, "repository_root", lambda: tmp_path)
    projects = tmp_path / "assets" / "projects"
    projects.mkdir(parents=True)
    (projects / ".gitkeep").touch()
    (projects / "project.yaml").write_text("project: forbidden\n", encoding="utf-8")

    with pytest.raises(AssertionError):
        test_current_main_projects_directory_is_empty()


def test_current_main_projects_directory_is_empty() -> None:
    if not is_main_guard_context():
        return
    repository_root = paths.repository_root()
    root = repository_root / "assets" / "projects"
    assert project_tree_errors(root) == []
    assert tracked_project_paths(repository_root) == ["assets/projects/.gitkeep"]


def test_empty_directory_marker_is_accepted(tmp_path: Path) -> None:
    (tmp_path / ".gitkeep").touch()
    assert project_tree_errors(tmp_path) == []


def test_symlinked_projects_directory_is_rejected(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    (target / ".gitkeep").touch()
    root = tmp_path / "projects"
    root.symlink_to(target, target_is_directory=True)
    assert project_tree_errors(root) == ["assets/projects must exist as a regular directory"]


def test_project_subdirectory_is_rejected(tmp_path: Path) -> None:
    (tmp_path / ".gitkeep").touch()
    (tmp_path / "dsh-credentials").mkdir()
    assert "project-specific entries are forbidden: ['dsh-credentials']" in project_tree_errors(tmp_path)


def test_project_yaml_is_rejected(tmp_path: Path) -> None:
    (tmp_path / ".gitkeep").touch()
    (tmp_path / "project.yaml").write_text("project: example\n", encoding="utf-8")
    assert "project-specific entries are forbidden: ['project.yaml']" in project_tree_errors(tmp_path)


def test_feature_flow_directory_is_rejected(tmp_path: Path) -> None:
    (tmp_path / ".gitkeep").touch()
    (tmp_path / "example-project").mkdir()
    (tmp_path / "example-project" / "feature-flow.md").write_text("flow", encoding="utf-8")
    assert project_tree_errors(tmp_path)


def test_deploy_directory_is_rejected(tmp_path: Path) -> None:
    (tmp_path / ".gitkeep").touch()
    (tmp_path / "example-project").mkdir()
    (tmp_path / "example-project" / "deploy.md").write_text("deploy", encoding="utf-8")
    assert project_tree_errors(tmp_path)


def test_repository_clone_directory_is_rejected(tmp_path: Path) -> None:
    (tmp_path / ".gitkeep").touch()
    (tmp_path / "example-project").mkdir()
    (tmp_path / "example-project" / "repository").mkdir()
    assert project_tree_errors(tmp_path)


def test_arbitrary_top_level_file_is_rejected(tmp_path: Path) -> None:
    (tmp_path / ".gitkeep").touch()
    (tmp_path / "notes.md").write_text("notes", encoding="utf-8")
    assert "project-specific entries are forbidden: ['notes.md']" in project_tree_errors(tmp_path)


def test_multiple_project_entries_are_all_reported(tmp_path: Path) -> None:
    (tmp_path / ".gitkeep").touch()
    (tmp_path / "z-project").mkdir()
    (tmp_path / "a-project").mkdir()
    errors = project_tree_errors(tmp_path)
    assert "project-specific entries are forbidden: ['a-project', 'z-project']" in errors


def test_nonempty_gitkeep_is_rejected(tmp_path: Path) -> None:
    (tmp_path / ".gitkeep").write_text("not empty", encoding="utf-8")
    assert "assets/projects/.gitkeep must be empty" in project_tree_errors(tmp_path)


def test_missing_gitkeep_is_rejected(tmp_path: Path) -> None:
    assert "assets/projects must contain a regular .gitkeep file" in project_tree_errors(tmp_path)


def test_directory_named_gitkeep_is_rejected(tmp_path: Path) -> None:
    (tmp_path / ".gitkeep").mkdir()
    assert "assets/projects must contain a regular .gitkeep file" in project_tree_errors(tmp_path)


def test_symlinked_gitkeep_is_rejected(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.touch()
    (tmp_path / ".gitkeep").symlink_to(target)
    assert "assets/projects must contain a regular .gitkeep file" in project_tree_errors(tmp_path)
