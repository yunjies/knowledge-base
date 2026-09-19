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
    """Return the repository root as a string path for `sys.path` injection."""
    return repository_root()


def ensure_repository_importable() -> Path:
    """Put the repository on `sys.path` so `packages.*` and `apps.*` import."""
    root = repository_root()
    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
    return root
