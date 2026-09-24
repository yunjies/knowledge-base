"""Locate the knowledge base and discover the documents the checks apply to.

Every check resolves the repository through `repository_root()` rather than
through its own relative depth, so the tree can be moved without touching an
assertion. The document sets are **discovered**, never listed: a new document
that nobody registers would otherwise be invisible to every check, which is the
failure this suite exists to prevent.

Two roots are refused rather than guessed at. `repository_root()` requires both
`_meta/` and `assets/`, because either marker alone matches directories that are
not this repository.
"""

from __future__ import annotations

import re
from pathlib import Path

SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", ".pytest_cache", ".uv-cache", ".agents"}

# `.agents/` is not a layer of this knowledge base: it is a skill distribution
# root, scanned by the harness rather than read as knowledge-base documentation.
# Its `reference/` files carry the criterion-register copies that ship with each
# skill, so their wording is the skill package's to decide. Judging them by this
# repository's writing constraints would report failures whose cause has nothing
# to do with this repository's documents.

# A project's own checkout is another repository with its own history and
# conventions; the knowledge base states that its internal layout is the
# project's decision. Its documents are therefore read here, never judged: the
# flow document the knowledge base owns sits *beside* the checkout, not inside
# it, and that is the one this suite checks.
CHECKOUT_PATTERN = re.compile(r"^assets/projects/[^/]+/[^/]+/")

# A document is a flow document when it carries a mermaid graph. The criterion is
# the graph, not the directory: a sample and a project's flow document are the
# same kind of artifact, and either may be added anywhere.
MERMAID_FENCE = re.compile(r"^```mermaid\s*$", re.MULTILINE)


def repository_root() -> Path:
    """Return the knowledge base this suite inspects."""
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "_meta").is_dir() and (candidate / "assets").is_dir():
            return candidate
    raise RuntimeError(f"could not locate the knowledge base above {__file__}")


def is_inside_checkout(path: Path) -> bool:
    """Report whether the document belongs to an included project's checkout."""
    return bool(CHECKOUT_PATTERN.match(str(path.relative_to(repository_root()))))



def _walk(root: Path):
    """Yield every markdown document under `root`, pruning the heavy directories.

    The pruning happens before descending, not after enumerating: a recursive
    glob visits every entry of a virtual environment or a `node_modules` tree
    before a filter can reject it, which costs minutes on a checkout that
    carries both.
    """
    stack = [root]
    while stack:
        directory = stack.pop()
        try:
            entries = sorted(directory.iterdir())
        except OSError:
            continue
        for entry in entries:
            if entry.is_dir():
                if entry.name in SKIP_DIRS:
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
    since a README is read as instructions too; and everything under `_meta/`,
    which holds the execution and writing constraints themselves. Leaving
    `_meta/` out was a real gap: the very document that states the counting rule
    was the one document the counting rule never read.
    """
    root = repository_root()
    meta = root / "_meta"
    out = [root / "AGENTS.md"]
    out.extend(path for path in all_documents() if path.name == "README.md")
    out.extend(path for path in all_documents() if meta in path.parents)
    return sorted({path for path in out if path.is_file()})


def relative(path: Path) -> str:
    """The document's path as it reads from the repository root."""
    return str(path.relative_to(repository_root()))
