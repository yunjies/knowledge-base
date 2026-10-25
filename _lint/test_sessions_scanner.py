from __future__ import annotations

from pathlib import Path

from _harness import paths


def test_walk_skips_root_sessions_without_descending(tmp_path: Path, monkeypatch) -> None:
    root_readme = tmp_path / "README.md"
    root_readme.write_text("root", encoding="utf-8")

    session_root = tmp_path / ".sessions"
    session_document = session_root / "synthetic-session" / "sample.md"
    session_document.parent.mkdir(parents=True)
    session_document.write_text("session", encoding="utf-8")

    nested_session_document = tmp_path / "ordinary" / ".sessions" / "sample.md"
    nested_session_document.parent.mkdir(parents=True)
    nested_session_document.write_text("nested", encoding="utf-8")

    real_iterdir = Path.iterdir

    def guarded_iterdir(directory: Path):
        assert directory != session_root
        return real_iterdir(directory)

    monkeypatch.setattr(Path, "iterdir", guarded_iterdir)
    documents = list(paths._walk(tmp_path))

    assert root_readme in documents
    assert session_document not in documents
    assert nested_session_document in documents
