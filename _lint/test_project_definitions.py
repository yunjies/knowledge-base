"""Main-branch project descriptors are metadata, not project content."""

from __future__ import annotations

import re
from pathlib import Path

from _harness import paths

REQUIRED_FIELDS = ("project", "repository", "content_branch", "description")
SAFE_DIRECTORY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
VALID_DESCRIPTOR = """project: example-project
repository: source-tree
content_branch: duoduo
description: A concise project definition.
"""


def parse_descriptor(text: str) -> dict[str, str]:
    """Read the deliberately small scalar-only project.yaml format."""
    values: dict[str, str] = {}
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            raise ValueError(f"not a scalar field: {line!r}")
        key, value = line.split(":", 1)
        if key in values:
            raise ValueError(f"duplicate field: {key}")
        values[key] = value.strip()
    return values


def metadata_errors(data: dict[str, str], directory_slug: str) -> list[str]:
    errors = []
    missing = sorted(set(REQUIRED_FIELDS) - data.keys())
    if missing:
        errors.append(f"missing required fields: {missing}")
    if set(data) != set(REQUIRED_FIELDS):
        errors.append("fields must be exactly the required metadata fields")
    if data.get("project") != directory_slug:
        errors.append("project must match its directory slug")
    repository = data.get("repository", "")
    if not SAFE_DIRECTORY.fullmatch(repository) or repository in {".", ".."}:
        errors.append("repository must be one safe directory name")
    branch = data.get("content_branch", "")
    if not branch or branch == "main" or branch.startswith("-") or branch.endswith("/"):
        errors.append("content_branch must be a confirmed non-main branch name")
    description = data.get("description", "")
    if not description or "\n" in description or "\r" in description:
        errors.append("description must be one nonempty line")
    return errors


def parse_errors(text: str, slug: str) -> list[str]:
    try:
        return metadata_errors(parse_descriptor(text), slug)
    except ValueError as error:
        return [str(error)]


def forbidden_project_content(root: Path) -> list[str]:
    """Only project.yaml may exist under a main-branch project directory."""
    if not root.exists():
        return []
    return sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.relative_to(root).as_posix() != "project.yaml"
    )


def test_current_project_descriptors_are_valid_and_metadata_only() -> None:
    root = paths.repository_root() / "assets" / "projects"
    offenders = []
    for directory in sorted(path for path in root.iterdir() if path.is_dir()):
        descriptor = directory / "project.yaml"
        if not descriptor.is_file():
            offenders.append(f"{directory.name}: project.yaml is missing")
            continue
        text = descriptor.read_text(encoding="utf-8")
        errors = parse_errors(text, directory.name)
        if errors:
            offenders.append(f"{directory.name}: {errors}")
        content = forbidden_project_content(directory)
        if content:
            offenders.append(f"{directory.name}: non-definition content {content}")
    assert offenders == [], f"main project directories must contain valid definitions only: {offenders}"


def test_valid_fixture_accepts_repository_distinct_from_project_slug() -> None:
    data = parse_descriptor(VALID_DESCRIPTOR)
    assert metadata_errors(data, "example-project") == []
    assert data["repository"] == "source-tree"


def test_missing_required_fields_are_rejected() -> None:
    for field in REQUIRED_FIELDS:
        data = parse_descriptor(VALID_DESCRIPTOR)
        del data[field]
        assert f"missing required fields: ['{field}']" in metadata_errors(data, "example-project")


def test_unknown_fields_are_rejected() -> None:
    data = parse_descriptor(VALID_DESCRIPTOR)
    data["notes"] = "project notes"
    assert "fields must be exactly the required metadata fields" in metadata_errors(data, "example-project")


def test_project_slug_must_match_directory() -> None:
    data = parse_descriptor(VALID_DESCRIPTOR)
    assert "project must match its directory slug" in metadata_errors(data, "different-slug")


def test_repository_must_be_a_single_safe_directory_name() -> None:
    for unsafe in ("../repo", "nested/repo", "/absolute", "", ".", "..", "repo name"):
        data = parse_descriptor(VALID_DESCRIPTOR)
        data["repository"] = unsafe
        assert "repository must be one safe directory name" in metadata_errors(data, "example-project")


def test_content_branch_must_be_non_main_and_named() -> None:
    for branch in ("", "main", "-bad", "bad/"):
        data = parse_descriptor(VALID_DESCRIPTOR)
        data["content_branch"] = branch
        assert "content_branch must be a confirmed non-main branch name" in metadata_errors(data, "example-project")


def test_description_must_be_present_and_single_line() -> None:
    for description in ("", "first\nsecond", "first\rsecond"):
        data = parse_descriptor(VALID_DESCRIPTOR)
        data["description"] = description
        assert "description must be one nonempty line" in metadata_errors(data, "example-project")


def test_duplicate_yaml_keys_are_rejected() -> None:
    duplicate = VALID_DESCRIPTOR + "project: other\n"
    assert any("duplicate field" in error for error in parse_errors(duplicate, "example-project"))


def test_non_scalar_yaml_shape_is_rejected() -> None:
    assert parse_errors("project: example-project\n- item\n", "example-project")


def test_flow_document_is_forbidden_project_content(tmp_path: Path) -> None:
    project = tmp_path / "example-project"
    project.mkdir()
    (project / "project.yaml").write_text(VALID_DESCRIPTOR, encoding="utf-8")
    (project / "feature-flow.md").write_text("flow", encoding="utf-8")
    assert forbidden_project_content(project) == ["feature-flow.md"]


def test_deploy_document_is_forbidden_project_content(tmp_path: Path) -> None:
    project = tmp_path / "example-project"
    project.mkdir()
    (project / "deploy.md").write_text("deployment", encoding="utf-8")
    assert forbidden_project_content(project) == ["deploy.md"]


def test_repository_clone_is_forbidden_project_content(tmp_path: Path) -> None:
    project = tmp_path / "example-project"
    (project / "source-tree").mkdir(parents=True)
    assert forbidden_project_content(project) == ["source-tree"]


def test_project_notes_and_other_files_are_forbidden(tmp_path: Path) -> None:
    project = tmp_path / "example-project"
    project.mkdir()
    (project / "notes.md").write_text("notes", encoding="utf-8")
    assert forbidden_project_content(project) == ["notes.md"]


def test_yaml_fixture_parser_rejects_duplicate_and_malformed_fields() -> None:
    for malformed in ("project example\n", "project: example\nproject: second\n"):
        assert parse_errors(malformed, "example-project")
