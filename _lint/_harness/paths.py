"""Locate the knowledge base and discover the documents the checks apply to.

Every check resolves the repository through `repository_root()` rather than
through its own relative depth, so the tree can be moved without touching an
assertion. The document sets are **discovered**, never listed: a new document
that nobody registers would otherwise be invisible to every check, which is the
failure this suite exists to prevent.

Two roots are refused rather than guessed at. `repository_root()` requires both
`knowledge-repository/` and `assets/`, because either marker alone matches directories that are
not this repository.
"""

from __future__ import annotations

import re
from pathlib import Path

SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", ".pytest_cache", ".uv-cache", ".agents", ".worktrees"}

# `.agents/` is not a layer of this knowledge base: it is a skill distribution
# root, scanned by the harness rather than read as knowledge-base documentation.
# Its `reference/` files carry the criterion-register copies that ship with each
# skill, so their wording is the skill package's to decide. Judging them by this
# repository's writing constraints would report failures whose cause has nothing
# to do with this repository's documents.

# A document is a flow document when it carries a mermaid graph. The criterion is
# the graph, not the directory: a sample and a project's flow document are the
# same kind of artifact, and either may be added anywhere.
MERMAID_FENCE = re.compile(r"^```mermaid\s*$", re.MULTILINE)


def repository_root() -> Path:
    """Return the knowledge base this suite inspects."""
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "knowledge-repository").is_dir() and (candidate / "assets").is_dir():
            return candidate
    raise RuntimeError(f"could not locate the knowledge base above {__file__}")


def is_inside_checkout(path: Path) -> bool:
    """Report whether a path is inside a Git checkout under assets/projects."""
    root = repository_root()
    try:
        relative = path.relative_to(root)
    except ValueError:
        return False
    if relative.parts[:2] != ("assets", "projects") or len(relative.parts) < 3:
        return False
    projects_root = root / "assets" / "projects"
    candidate = path if path.is_dir() else path.parent
    while candidate != projects_root:
        if (candidate / ".git").exists():
            return True
        candidate = candidate.parent
    return False



def _walk(root: Path):
    """Yield every markdown document under `root`, pruning before descending.

    Two prunes happen before a directory is descended into: the heavy
    directories (`SKIP_DIRS`), and an included project's checkout — the same
    scope `is_inside_checkout` states, applied where it costs nothing. A
    recursive glob or a filter-after-enumeration visits every entry of a
    `node_modules` tree or a checkout before a filter can reject it; on a
    filesystem where one stat runs ~1.4ms that is minutes per pass, and the
    discovery functions run once per test that asks for them.
    """
    stack = [root]
    while stack:
        directory = stack.pop()
        try:
            entries = sorted(directory.iterdir())
        except OSError:
            continue
        for entry in entries:
            if directory == root and entry.name == ".sessions":
                continue
            if entry.is_dir():
                if entry.name in SKIP_DIRS:
                    continue
                if is_inside_checkout(entry):
                    continue
                stack.append(entry)
            elif entry.suffix == ".md":
                yield entry


def all_documents() -> list[Path]:
    """Every markdown document the knowledge base itself carries.

    Walks the repository rather than a set of known directories, so a new
    top-level area is covered the day it appears. Documents inside an included
    project's checkout are withheld, per `is_inside_checkout`.
    """
    return [path for path in _walk(repository_root()) if not is_inside_checkout(path)]


def flow_documents() -> list[Path]:
    """The documents that carry a mermaid graph, and so owe F01-F08."""
    out = []
    for path in all_documents():
        if MERMAID_FENCE.search(path.read_text(encoding="utf-8")):
            out.append(path)
    return out


def instruction_documents() -> list[Path]:
    """The documents that instruct an agent.

    Three sets, discovered rather than listed. The root file; every README,
    since a README is read as instructions too; and everything under `knowledge-repository/`,
    which holds the execution and writing constraints themselves. Leaving
    `knowledge-repository/` out was a real gap: the very document that states the counting rule
    was the one document the counting rule never read.
    """
    root = repository_root()
    meta = root / "knowledge-repository"
    out = [root / "AGENTS.md"]
    out.extend(path for path in all_documents() if path.name == "README.md")
    out.extend(path for path in all_documents() if meta in path.parents)
    return sorted({path for path in out if path.is_file()})


def relative(path: Path) -> str:
    """The document's path as it reads from the repository root."""
    return str(path.relative_to(repository_root()))
