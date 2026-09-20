"""Mirrors `src/apps/worker.py` and `src/apps/scheduler.py`: the long-running processes."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from _harness.paths import repository_root


@pytest.mark.parametrize("entrypoint", ["src/apps/worker.py", "src/apps/scheduler.py"])
def test_entrypoint_exposes_a_main_callable(repo: Path, entrypoint: str) -> None:
    source = (repo / entrypoint).read_text()
    tree = ast.parse(source)
    functions = {
        node.name for node in tree.body if isinstance(node, ast.FunctionDef)
    }
    assert "main" in functions, f"{entrypoint} must expose main()"
    assert 'if __name__ == "__main__":' in source


@pytest.mark.parametrize("entrypoint", ["src/apps/worker.py", "src/apps/scheduler.py"])
def test_entrypoint_shuts_down_on_interrupt(repo: Path, entrypoint: str) -> None:
    """Both processes must exit cleanly on SIGINT rather than traceback."""
    source = (repo / entrypoint).read_text()
    assert "KeyboardInterrupt" in source


@pytest.mark.parametrize("entrypoint", ["src/apps/worker.py", "src/apps/scheduler.py"])
def test_entrypoint_emits_startup_and_shutdown_logs(repo: Path, entrypoint: str) -> None:
    source = (repo / entrypoint).read_text()
    assert "started" in source
    assert "stopped" in source


def test_worker_is_not_yet_attached_to_the_task_queue(repo: Path) -> None:
    """Record the current shape: the worker sleeps rather than consuming tasks.

    This is a deliberate statement about the checkout, so that wiring the runner
    into the worker shows up as this test failing.
    """
    source = (repo / "src/apps/worker.py").read_text()
    assert "TaskRunner" not in source
    assert "time.sleep" in source


def test_logging_module_configures_structured_output(repo: Path) -> None:
    source = (repo / "src/apps/infrastructure/logging.py").read_text()
    assert "configure_logging" in source
    assert "get_logger" in source
