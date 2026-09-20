"""Mirrors `packages/application/tasks`: task runner failure classification."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import pytest

from packages.application.tasks.runner import FakeAdapter, TaskRunner
from packages.application.tasks.service import TaskService
from packages.infrastructure.db.models import Base


@pytest.fixture
def runner_factory():
    def build(adapters: dict[str, object]) -> tuple[TaskRunner, TaskService]:
        engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(engine)
        session = Session(engine)
        service = TaskService(session)
        return TaskRunner(service, adapters), service

    return build


def test_successful_run_records_the_adapter_result(runner_factory) -> None:
    adapter = FakeAdapter(result={"ok": True})
    runner, service = runner_factory({"demo": adapter})
    task = service.submit(kind="demo", idempotency_key="k1", payload={"a": 1})

    runner.run_once(task.id)

    refreshed = service.repository.get(task.id)
    assert refreshed.status == "succeeded"
    assert refreshed.result_json["payload"] == {"a": 1}
    assert adapter.calls == 1


def test_missing_adapter_fails_without_retry(runner_factory) -> None:
    runner, service = runner_factory({})
    task = service.submit(kind="unknown", idempotency_key="k2")

    runner.run_once(task.id)

    refreshed = service.repository.get(task.id)
    assert refreshed.status == "failed"
    assert refreshed.retryable is False


def test_timeout_is_classified_retryable(runner_factory) -> None:
    adapter = FakeAdapter(error=TimeoutError("too slow"))
    runner, service = runner_factory({"demo": adapter})
    task = service.submit(kind="demo", idempotency_key="k3")

    runner.run_once(task.id)

    assert service.repository.get(task.id).retryable is True


def test_generic_error_is_classified_terminal(runner_factory) -> None:
    adapter = FakeAdapter(error=RuntimeError("logic bug"))
    runner, service = runner_factory({"demo": adapter})
    task = service.submit(kind="demo", idempotency_key="k4")

    runner.run_once(task.id)

    assert service.repository.get(task.id).retryable is False


def test_runner_rejects_a_task_that_is_not_queued(runner_factory) -> None:
    adapter = FakeAdapter()
    runner, service = runner_factory({"demo": adapter})
    task = service.submit(kind="demo", idempotency_key="k5")
    runner.run_once(task.id)

    with pytest.raises(ValueError):
        runner.run_once(task.id)
    assert adapter.calls == 1
