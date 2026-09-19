"""Mirrors `packages/infrastructure/db`: schema, task lifecycle, audit trail."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import Session

from packages.infrastructure.db.models import (
    AuditEvent,
    Base,
    JobAttempt,
    JobLog,
    TaskRecord,
)
from packages.infrastructure.db.repositories import TaskRepository


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db


def test_schema_declares_the_control_plane_tables() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    tables = set(inspect(engine).get_table_names())
    for expected in (
        "media_entities",
        "media_files",
        "library_scan_reports",
        "media_libraries",
        "media_library_paths",
        "provider_configs",
        "metadata_match_sessions",
        "agent_sessions",
        "agent_messages",
        "acquisition_approvals",
        "download_tasks",
        "wishlist_items",
        "scheduled_jobs",
        "job_attempts",
        "job_logs",
        "audit_events",
    ):
        assert expected in tables, f"missing table: {expected}"


def test_new_task_starts_queued_and_claimable(session: Session) -> None:
    repo = TaskRepository(session)
    task = repo.create_task(
        kind="acquisition.download", idempotency_key="key-1", payload={"a": 1}
    )
    assert task.status == "queued"

    claimed = repo.claim(task.id)
    assert claimed.status == "running"
    assert session.scalars(select(JobAttempt)).one().status == "running"


def test_repository_rejects_reclaiming_a_running_task(session: Session) -> None:
    repo = TaskRepository(session)
    task = repo.create_task(kind="k", idempotency_key="key-2")
    repo.claim(task.id)
    with pytest.raises(ValueError):
        repo.claim(task.id)


def test_succeed_requires_running_and_records_result(session: Session) -> None:
    repo = TaskRepository(session)
    task = repo.create_task(kind="k", idempotency_key="key-3")
    with pytest.raises(ValueError):
        repo.succeed(task.id, {"ok": True})

    repo.claim(task.id)
    done = repo.succeed(task.id, {"ok": True})
    assert done.status == "succeeded"
    assert done.result_json == {"ok": True}


def test_failed_task_retries_only_when_marked_retryable(session: Session) -> None:
    repo = TaskRepository(session)
    terminal = repo.create_task(kind="k", idempotency_key="key-4")
    repo.claim(terminal.id)
    repo.fail(terminal.id, "boom", retryable=False)
    with pytest.raises(ValueError):
        repo.retry(terminal.id)


def test_retryable_failure_returns_to_queue(session: Session) -> None:
    repo = TaskRepository(session)
    task = repo.create_task(kind="k", idempotency_key="key-5")
    repo.claim(task.id)
    repo.fail(task.id, "timeout", retryable=True)
    assert repo.retry(task.id).status == "queued"


def test_idempotency_key_is_unique(session: Session) -> None:
    repo = TaskRepository(session)
    repo.create_task(kind="k", idempotency_key="same-key")
    repo.create_task(kind="k", idempotency_key="same-key")
    rows = session.scalars(
        select(TaskRecord).where(TaskRecord.idempotency_key == "same-key")
    ).all()
    assert len(rows) == 1, "duplicate submission must reuse the existing task"


def test_logs_and_audits_are_persisted(session: Session) -> None:
    repo = TaskRepository(session)
    task = repo.create_task(kind="k", idempotency_key="key-6")
    repo.log(task.id, "started", {"step": 1})
    repo.audit(
        task.id,
        action="acquisition.approval.created",
        outcome="pending",
        details={"a": "b"},
    )
    assert session.scalars(select(JobLog)).one().message == "started"
    assert session.scalars(select(AuditEvent)).one().action == (
        "acquisition.approval.created"
    )


def test_cancelling_a_finished_task_is_rejected(session: Session) -> None:
    repo = TaskRepository(session)
    task = repo.create_task(kind="k", idempotency_key="key-7")
    repo.claim(task.id)
    repo.succeed(task.id, {})
    with pytest.raises(ValueError):
        repo.cancel(task.id, reason="too late")
