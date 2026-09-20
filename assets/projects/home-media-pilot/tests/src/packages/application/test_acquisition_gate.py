"""Mirrors `packages/application/acquisition`: preview, approval, gated execution.

The execution path is exercised only through fake adapters: the repository ships
no enabled download mutation adapter, so the gate itself is what is under test.
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from packages.frameworks.errors import ProviderError
from packages.application.acquisition import AcquisitionService
from packages.contracts.acquisition import AcquisitionPreviewRequest
from packages.domain.states import ErrorCategory
from packages.infrastructure.db.models import AcquisitionApproval, AuditEvent, Base


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db


def _request(**overrides: Any) -> AcquisitionPreviewRequest:
    payload: dict[str, Any] = {
        "source": "mteam",
        "external_id": "12345",
        "title": "Dune (2021)",
        "category": "movies",
        "save_path": "/downloads/movies",
    }
    payload.update(overrides)
    return AcquisitionPreviewRequest(**payload)


class FakeArtifact:
    def __init__(self) -> None:
        self.calls = 0

    def get_artifact(self, external_id: str) -> str:
        self.calls += 1
        return "magnet:?xt=urn:btih:deadbeef"


class FakeDownloader:
    def __init__(self, *, readback_hash: str | None = None) -> None:
        self.added: list[tuple[str, str, str]] = []
        self.readback_hash = readback_hash

    def add(self, artifact: str, *, category: str, save_path: str) -> str:
        self.added.append((artifact, category, save_path))
        return self.readback_hash or "task-hash-1"

    def readback(self, external_task_id: str) -> dict[str, Any]:
        return {"hash": external_task_id, "progress": 0.0}


def test_preview_is_non_mutating_and_reports_mutation_flag(session: Session) -> None:
    service = AcquisitionService(session)
    preview = service.preview(_request())
    assert preview.mutation_enabled is False
    assert preview.duplicate_task is False
    assert session.scalars(select(AcquisitionApproval)).all() == []


def test_preview_idempotency_key_is_stable_for_equal_requests(session: Session) -> None:
    service = AcquisitionService(session)
    first = service.preview(_request())
    second = service.preview(_request())
    assert first.idempotency_key == second.idempotency_key


def test_preview_idempotency_key_changes_with_parameters(session: Session) -> None:
    service = AcquisitionService(session)
    base = service.preview(_request()).idempotency_key
    other = service.preview(_request(save_path="/downloads/other")).idempotency_key
    assert base != other


def test_create_approval_is_idempotent_and_audited(session: Session) -> None:
    service = AcquisitionService(session)
    preview = service.preview(_request())

    first = service.create_approval(preview)
    second = service.create_approval(preview)

    assert first.id == second.id
    assert first.status == "pending"
    assert len(session.scalars(select(AcquisitionApproval)).all()) == 1
    assert session.scalars(select(AuditEvent)).one().action == (
        "acquisition.approval.created"
    )


def test_approving_a_pending_record_succeeds(session: Session) -> None:
    service = AcquisitionService(session)
    approval = service.create_approval(service.preview(_request()))
    assert service.approve(approval.id).status == "approved"


def test_approving_twice_is_rejected(session: Session) -> None:
    service = AcquisitionService(session)
    approval = service.create_approval(service.preview(_request()))
    service.approve(approval.id)
    with pytest.raises(ValueError):
        service.approve(approval.id)


def test_execution_is_blocked_while_mutation_capability_is_disabled(
    session: Session,
) -> None:
    service = AcquisitionService(session, mutation_enabled=False)
    approval = service.create_approval(service.preview(_request()))
    service.approve(approval.id)

    downloader = FakeDownloader()
    with pytest.raises(ProviderError) as excinfo:
        service.execute(approval.id, FakeArtifact(), downloader)

    assert excinfo.value.category is ErrorCategory.BLOCKED
    assert downloader.added == [], "disabled mutation must not reach the downloader"


def test_execution_is_blocked_without_approval_even_when_enabled(
    session: Session,
) -> None:
    service = AcquisitionService(session, mutation_enabled=True)
    approval = service.create_approval(service.preview(_request()))

    downloader = FakeDownloader()
    with pytest.raises(ProviderError) as excinfo:
        service.execute(approval.id, FakeArtifact(), downloader)

    assert excinfo.value.category is ErrorCategory.BLOCKED
    assert downloader.added == [], "pending approval must not submit a download"


def test_execution_requires_readback_matching_submitted_task(session: Session) -> None:
    service = AcquisitionService(session, mutation_enabled=True)
    approval = service.create_approval(service.preview(_request()))
    service.approve(approval.id)

    class MismatchedDownloader(FakeDownloader):
        def readback(self, external_task_id: str) -> dict[str, Any]:
            return {"hash": "a-different-hash"}

    with pytest.raises(ProviderError) as excinfo:
        service.execute(approval.id, FakeArtifact(), MismatchedDownloader())

    assert excinfo.value.category is ErrorCategory.BUSINESS
    stored = session.get(AcquisitionApproval, approval.id)
    assert stored.status in {"failed", "partial"}


def test_execution_is_replayed_from_the_task_on_second_call(session: Session) -> None:
    """A completed task under an approved record replays instead of resubmitting.

    Reaching the replay branch requires the approval to still read `approved`
    while its task already succeeded, so the record is put back into that state
    after the first submission.
    """
    service = AcquisitionService(session, mutation_enabled=True)
    approval = service.create_approval(service.preview(_request()))
    service.approve(approval.id)

    artifacts, downloader = FakeArtifact(), FakeDownloader()
    first = service.execute(approval.id, artifacts, downloader)

    session.get(AcquisitionApproval, approval.id).status = "approved"
    session.flush()
    second = service.execute(approval.id, artifacts, downloader)

    assert first.status == second.status == "submitted"
    assert first.task_id == second.task_id
    assert artifacts.calls == 1, "idempotent replay must not fetch the artifact twice"
    assert len(downloader.added) == 1, "idempotent replay must not resubmit"


def test_completed_approval_is_not_executable_again(session: Session) -> None:
    """Once completed the gate rejects re-execution rather than resubmitting."""
    service = AcquisitionService(session, mutation_enabled=True)
    approval = service.create_approval(service.preview(_request()))
    service.approve(approval.id)

    artifacts, downloader = FakeArtifact(), FakeDownloader()
    service.execute(approval.id, artifacts, downloader)

    with pytest.raises(ProviderError) as excinfo:
        service.execute(approval.id, artifacts, downloader)
    assert excinfo.value.category is ErrorCategory.BLOCKED
    assert len(downloader.added) == 1


def test_successful_execution_marks_approval_completed(session: Session) -> None:
    service = AcquisitionService(session, mutation_enabled=True)
    approval = service.create_approval(service.preview(_request()))
    service.approve(approval.id)

    result = service.execute(approval.id, FakeArtifact(), FakeDownloader())

    stored = session.get(AcquisitionApproval, approval.id)
    assert stored.status == "completed"
    assert stored.external_task_id == result.external_task_id


def test_state_view_keeps_landing_and_visibility_independent(session: Session) -> None:
    service = AcquisitionService(session)
    approval = service.create_approval(service.preview(_request()))

    state = service.state(approval.id)

    facts = {fact.stage: fact.status for fact in state.facts}
    assert facts["tracker"] == "verified"
    assert facts["approval"] == "pending"
    assert facts["jellyfin"] == "unknown"
    assert facts["filesystem"] == "unknown"
    assert "magnet" not in str(state.model_dump(mode="json")), "artifact must not leak"


def test_state_view_reports_filesystem_landing_when_probed(
    session: Session, tmp_path
) -> None:
    from packages.providers.storage.filesystem import FilesystemLandingReadOnlyAdapter

    landing = tmp_path / "landing"
    landing.mkdir()
    service = AcquisitionService(session)
    approval = service.create_approval(
        service.preview(_request(save_path=str(landing)))
    )

    state = service.state(
        approval.id, filesystem_adapter=FilesystemLandingReadOnlyAdapter()
    )

    facts = {fact.stage: fact.status for fact in state.facts}
    assert facts["filesystem"] == "observed"
    assert facts["jellyfin"] == "unknown", "landing must not imply library visibility"


def test_unknown_approval_is_rejected(session: Session) -> None:
    from uuid import uuid4

    service = AcquisitionService(session)
    with pytest.raises(KeyError):
        service.approve(uuid4())
