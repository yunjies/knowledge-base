"""Mirrors `packages/infrastructure/library`: logical path mapping and traversal guard."""

from __future__ import annotations

from pathlib import Path

import pytest

from packages.infrastructure.library.paths import LogicalPathMapper, PathOutsideLibrary


@pytest.fixture
def mapper(tmp_path: Path) -> LogicalPathMapper:
    return LogicalPathMapper({"movies": tmp_path / "movies", "tv": tmp_path / "tv"})


def test_resolve_maps_logical_root_to_physical_path(mapper: LogicalPathMapper, tmp_path: Path) -> None:
    assert mapper.resolve("movies") == (tmp_path / "movies").resolve()
    assert mapper.resolve("movies", "Dune (2021)/Dune.mkv") == (
        tmp_path / "movies" / "Dune (2021)" / "Dune.mkv"
    ).resolve()


def test_unknown_logical_root_is_rejected(mapper: LogicalPathMapper) -> None:
    with pytest.raises(KeyError):
        mapper.resolve("music")


@pytest.mark.parametrize(
    "relative",
    ["../secrets.txt", "../../etc/passwd", "sub/../../outside.txt"],
)
def test_parent_traversal_escaping_the_root_is_rejected(
    mapper: LogicalPathMapper, relative: str
) -> None:
    with pytest.raises(PathOutsideLibrary):
        mapper.resolve("movies", relative)


def test_traversal_that_stays_inside_the_root_is_allowed(
    mapper: LogicalPathMapper, tmp_path: Path
) -> None:
    resolved = mapper.resolve("movies", "sub/../Dune.mkv")
    assert resolved == (tmp_path / "movies" / "Dune.mkv").resolve()


def test_logical_roots_are_reported_sorted(mapper: LogicalPathMapper) -> None:
    assert mapper.logical_roots() == ("movies", "tv")
