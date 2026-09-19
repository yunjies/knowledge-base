"""Shared pytest wiring for the mirrored suite.

The repository under test is imported from `src/Home-Media-Pilot`; this file is
the single place that performs that injection.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _harness.paths import (  # noqa: E402
    ensure_repository_importable,
    repository_root,
)

ensure_repository_importable()


@pytest.fixture(scope="session")
def repo() -> Path:
    return repository_root()
