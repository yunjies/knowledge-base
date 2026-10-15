"""The main branch keeps no project-specific material."""

from __future__ import annotations

import subprocess
from pathlib import Path

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


def test_current_main_projects_directory_is_empty() -> None:
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
