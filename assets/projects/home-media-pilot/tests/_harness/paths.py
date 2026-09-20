"""Make the mirrored test tree importable and resolve the repository under test.

Every test module resolves the repository through `repository_root()` rather than
through its own relative depth, so the tree can be re-mirrored without touching
the assertions.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_DIR_NAME = "Home-Media-Pilot"


def repository_root() -> Path:
    """Return the checkout the suite inspects.

    The mirror sits beside `src/`, so the repository is located under `src/`
    starting from the directory that holds this mirror.
    """
    for candidate in Path(__file__).resolve().parents:
        repo = candidate / "src" / REPO_DIR_NAME
        if (repo / "pyproject.toml").is_file():
            return repo
    raise RuntimeError(f"could not locate src/{REPO_DIR_NAME} above {__file__}")


def repository_src() -> Path:
    """Return the directory holding the importable packages.

    The repository keeps its business code under its own `src/`, so the
    top-level import names (`packages.*`, `apps.*`) resolve from there rather
    than from the repository root, which carries only build and deploy inputs.
    """
    return repository_root() / "src"


def ensure_repository_importable() -> Path:
    """Put the package directory on `sys.path` so `packages.*` and `apps.*` import."""
    root = repository_root()
    src_str = str(repository_src())
    if src_str not in sys.path:
        sys.path.insert(0, src_str)
    return root
