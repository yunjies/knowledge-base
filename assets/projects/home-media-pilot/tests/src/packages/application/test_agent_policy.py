"""Mirrors `packages/application/agent`: the registered-tool policy boundary.

`AgentService` reaches `packages.infrastructure.secrets`, which the checkout does
not contain. The import is deferred into a fixture so each test in this file
reports a failure with the cause, instead of being excused or aborting
collection.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from packages.infrastructure.db.models import Base
from packages.contracts.agent import AgentToolRequest

BLOCK_CAUSE = "packages.infrastructure.secrets"


def _load_agent_service():
    """Import AgentService, turning a blocked import into a test failure."""
    import importlib

    try:
        return importlib.import_module("packages.application.agent").AgentService
    except ModuleNotFoundError as exc:
        assert BLOCK_CAUSE not in str(exc), (
            "packages.application.agent cannot be imported: it reaches the "
            f"absent module {BLOCK_CAUSE}, so no Agent policy can run. "
            "Restore that module to make these tests pass."
        )
        raise


class _FakeQb:
    def health(self) -> dict[str, object]:
        return {"state": "verified_readonly"}

    def tasks(self) -> list[dict[str, object]]:
        return []


class _FakeMteam:
    def search(self, request: object) -> list[dict[str, object]]:
        return []


@pytest.fixture
def service() -> object:
    """Build the service, or yield an object that fails when first used.

    A fixture that raises is reported as an error rather than a failure, so the
    blocked-import case is surfaced inside each test body instead.
    """
    try:
        agent_service = _load_agent_service()
    except AssertionError as exc:
        yield _Unavailable(exc)
        return
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield agent_service(session, qb=_FakeQb(), mteam=_FakeMteam())


class _Unavailable:
    """Stand-in that turns any use into the blocked-import failure."""

    def __init__(self, cause: AssertionError) -> None:
        self._cause = cause

    def __getattr__(self, name: str):
        raise AssertionError(str(self._cause))


def test_only_registered_tools_are_exposed(service) -> None:
    names = {tool.name for tool in service.tools()}
    assert names == {
        "library.list",
        "library.resources",
        "metadata.preview",
        "tracker.search",
        "qb.health",
        "qb.tasks",
        "acquisition.preview",
        "acquisition.confirm",
    }


def test_unregistered_tool_is_blocked(service) -> None:
    result = service.invoke(AgentToolRequest(tool="shell.exec", mode="read"))
    assert result.status == "blocked"
    assert result.error_code == "unregistered_tool"


@pytest.mark.parametrize("tool", ["sql.query", "credential.read", "secret.dump", "token.get"])
def test_unsafe_tool_names_are_blocked(service, tool: str) -> None:
    result = service.invoke(AgentToolRequest(tool=tool, mode="read"))
    assert result.status == "blocked"


@pytest.mark.parametrize(
    "key", ["api_key", "password", "authorization", "token", "credential", "secret"]
)
def test_sensitive_arguments_are_blocked(service, key: str) -> None:
    result = service.invoke(
        AgentToolRequest(tool="library.list", mode="read", arguments={key: "value"})
    )
    assert result.status == "blocked"
    assert result.error_code == "sensitive_arguments"


def test_sensitive_arguments_are_blocked_at_nested_depth(service) -> None:
    result = service.invoke(
        AgentToolRequest(
            tool="library.list",
            mode="read",
            arguments={"outer": {"inner": [{"password": "x"}]}},
        )
    )
    assert result.status == "blocked"


def test_read_only_tool_runs_in_read_mode(service) -> None:
    result = service.invoke(AgentToolRequest(tool="qb.health", mode="read"))
    assert result.status == "ok"


def test_confirming_tool_requires_confirm_mode(service) -> None:
    arguments = {
        "source": "mteam",
        "external_id": "1",
        "title": "Dune",
        "category": "movies",
        "save_path": "/downloads/movies",
    }
    blocked = service.invoke(
        AgentToolRequest(tool="acquisition.confirm", mode="preview", arguments=arguments)
    )
    assert blocked.status == "blocked"
    assert blocked.error_code == "confirmation_required"


def test_preview_tool_requires_preview_mode(service) -> None:
    result = service.invoke(
        AgentToolRequest(
            tool="acquisition.preview",
            mode="confirm",
            arguments={
                "source": "mteam",
                "external_id": "1",
                "title": "Dune",
                "category": "movies",
                "save_path": "/downloads/movies",
            },
        )
    )
    assert result.status == "blocked"
    assert result.error_code == "preview_required"


def test_confirm_requires_the_token_issued_by_preview(service) -> None:
    arguments = {
        "source": "mteam",
        "external_id": "1",
        "title": "Dune",
        "category": "movies",
        "save_path": "/downloads/movies",
    }
    preview = service.invoke(
        AgentToolRequest(tool="acquisition.preview", mode="preview", arguments=arguments)
    )
    assert preview.status == "preview"
    assert preview.confirmation_token

    mismatched = service.invoke(
        AgentToolRequest(
            tool="acquisition.confirm",
            mode="confirm",
            arguments=arguments,
            confirmation_token="not-the-token",
        )
    )
    assert mismatched.status == "blocked"
    assert mismatched.error_code == "confirmation_token_mismatch"


def test_confirm_with_the_issued_token_creates_an_approved_record(
    service,
) -> None:
    arguments = {
        "source": "mteam",
        "external_id": "1",
        "title": "Dune",
        "category": "movies",
        "save_path": "/downloads/movies",
    }
    preview = service.invoke(
        AgentToolRequest(tool="acquisition.preview", mode="preview", arguments=arguments)
    )
    confirmed = service.invoke(
        AgentToolRequest(
            tool="acquisition.confirm",
            mode="confirm",
            arguments=arguments,
            confirmation_token=preview.confirmation_token,
        )
    )
    assert confirmed.status == "confirmed"
    assert confirmed.data["status"] == "approved"


def test_invalid_arguments_yield_invalid_request(service) -> None:
    result = service.invoke(
        AgentToolRequest(tool="library.resources", mode="read", arguments={"library_id": "not-a-uuid"})
    )
    assert result.status == "error"
    assert result.error_code == "invalid_request"


def test_agent_never_exposes_execution_of_a_download(service) -> None:
    """The Agent tool set must contain no tool that submits a download."""
    names = {tool.name for tool in service.tools()}
    assert not any("execute" in name or "download" in name for name in names)
