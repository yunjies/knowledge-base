"""Mirrors `packages/application/library`: scanning, title derivation, indexing."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from packages.application.library.scan import LibraryScanner, clean_media_title
from packages.application.library.service import LibraryService
from packages.infrastructure.db.models import Base, MediaEntity, MediaFile
from packages.infrastructure.library.paths import LogicalPathMapper


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("Dune.2021.2160p.WEB-DL.x265.mkv", "Dune"),
        ("Dune (2021).mkv", "Dune"),
        ("The.Matrix.1999.1080p.BluRay.x264-GROUP.mkv", "The Matrix"),
        ("Severance.S02E01.1080p.WEB.mkv", "Severance"),
    ],
)
def test_title_derivation_strips_release_tail(filename: str, expected: str) -> None:
    assert clean_media_title(filename) == expected


def test_scan_collects_media_and_subtitles(tmp_path: Path) -> None:
    root = tmp_path / "movies"
    root.mkdir()
    (root / "Dune (2021).mkv").write_bytes(b"movie")
    (root / "Dune (2021).zh.srt").write_text("1\n")
    (root / "cover.jpg").write_bytes(b"image")

    result = LibraryScanner(LogicalPathMapper({"movies": root})).scan("movies")
    kinds = {item.relative_path: item.media_kind for item in result.items}
    assert kinds == {"Dune (2021).mkv": "movie", "Dune (2021).zh.srt": "subtitle"}


def test_scan_detects_season_and_episode(tmp_path: Path) -> None:
    root = tmp_path / "tv"
    root.mkdir()
    (root / "Severance.S02E03.mkv").write_bytes(b"episode")

    result = LibraryScanner(LogicalPathMapper({"tv": root})).scan("tv")
    item = result.items[0]
    assert item.media_kind == "episode"
    assert (item.season, item.episode) == (2, 3)


def test_scan_skips_hidden_paths(tmp_path: Path) -> None:
    root = tmp_path / "movies"
    hidden = root / ".trash"
    hidden.mkdir(parents=True)
    (hidden / "Dune.mkv").write_bytes(b"x")
    (root / "Visible.mkv").write_bytes(b"y")

    result = LibraryScanner(LogicalPathMapper({"movies": root})).scan("movies")
    assert [item.relative_path for item in result.items] == ["Visible.mkv"]


def test_scan_does_not_modify_the_filesystem(tmp_path: Path) -> None:
    root = tmp_path / "movies"
    root.mkdir()
    media = root / "Dune.mkv"
    media.write_bytes(b"movie")
    before = sorted(p.name for p in root.iterdir())

    LibraryScanner(LogicalPathMapper({"movies": root})).scan("movies")
    assert sorted(p.name for p in root.iterdir()) == before
    assert media.read_bytes() == b"movie"


def test_scan_reports_removed_files_against_previous_result(tmp_path: Path) -> None:
    root = tmp_path / "movies"
    root.mkdir()
    (root / "A.mkv").write_bytes(b"a")
    (root / "B.mkv").write_bytes(b"b")
    scanner = LibraryScanner(LogicalPathMapper({"movies": root}))

    first = scanner.scan("movies")
    (root / "B.mkv").unlink()
    second = scanner.scan("movies", previous=first)

    assert first.total_files == 2
    assert second.total_files == 1
    assert second.removed_files == 1


def test_service_indexes_entities_and_files(session: Session, tmp_path: Path) -> None:
    root = tmp_path / "movies"
    root.mkdir()
    (root / "Dune.mkv").write_bytes(b"movie")

    LibraryService(session, {"movies": root}).scan("movies")

    assert session.scalars(select(MediaEntity)).one().title == "Dune"
    assert session.scalars(select(MediaFile)).one().path == "movies/Dune.mkv"


def test_service_keeps_same_title_in_two_roots_separate(
    session: Session, tmp_path: Path
) -> None:
    tv, movies = tmp_path / "tv", tmp_path / "movies"
    tv.mkdir()
    movies.mkdir()
    (tv / "Dune.mkv").write_bytes(b"tv")
    (movies / "Dune.mkv").write_bytes(b"movie")

    service = LibraryService(session, {"tv": tv, "movies": movies})
    service.scan("tv")
    service.scan("movies")

    entities = session.scalars(
        select(MediaEntity).order_by(MediaEntity.source_logical_root)
    ).all()
    assert [e.source_logical_root for e in entities] == ["movies", "tv"]
    assert len(entities) == 2, "same title in two logical roots must not merge"


def test_service_updates_fingerprint_when_file_changes(
    session: Session, tmp_path: Path
) -> None:
    root = tmp_path / "movies"
    root.mkdir()
    media = root / "Dune.mkv"
    media.write_bytes(b"short")

    service = LibraryService(session, {"movies": root})
    service.scan("movies")
    first = session.scalars(select(MediaFile)).one().fingerprint

    media.write_bytes(b"a much longer payload")
    result = service.scan("movies")

    assert session.scalars(select(MediaFile)).one().fingerprint != first
    assert result.changed_files == 1


def test_repeated_scan_does_not_duplicate_rows(session: Session, tmp_path: Path) -> None:
    root = tmp_path / "movies"
    root.mkdir()
    (root / "Dune.mkv").write_bytes(b"movie")
    service = LibraryService(session, {"movies": root})

    service.scan("movies")
    service.scan("movies")

    assert len(session.scalars(select(MediaFile)).all()) == 1
    assert len(session.scalars(select(MediaEntity)).all()) == 1
