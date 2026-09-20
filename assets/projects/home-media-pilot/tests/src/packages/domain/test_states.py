"""Mirrors `packages/domain`: lifecycle states and error categories."""

from __future__ import annotations

import pytest

from packages.domain.states import (
    ErrorCategory,
    InvalidTransition,
    transition_download,
)
from packages.domain.downloads import DownloadStatus


def test_pending_may_only_move_to_queued_or_cancelled() -> None:
    assert transition_download(DownloadStatus.PENDING, DownloadStatus.QUEUED) == (
        DownloadStatus.QUEUED
    )
    assert transition_download(DownloadStatus.PENDING, DownloadStatus.CANCELLED) == (
        DownloadStatus.CANCELLED
    )
    with pytest.raises(InvalidTransition):
        transition_download(DownloadStatus.PENDING, DownloadStatus.COMPLETED)


def test_running_may_complete_fail_or_cancel() -> None:
    for target in (
        DownloadStatus.COMPLETED,
        DownloadStatus.FAILED,
        DownloadStatus.CANCELLED,
    ):
        assert transition_download(DownloadStatus.RUNNING, target) == target


@pytest.mark.parametrize(
    "terminal", [DownloadStatus.COMPLETED, DownloadStatus.CANCELLED]
)
def test_terminal_states_have_no_outgoing_transitions(terminal: DownloadStatus) -> None:
    for target in DownloadStatus:
        with pytest.raises(InvalidTransition):
            transition_download(terminal, target)


def test_failed_task_is_retryable_only_back_to_queued() -> None:
    assert transition_download(DownloadStatus.FAILED, DownloadStatus.QUEUED) == (
        DownloadStatus.QUEUED
    )
    with pytest.raises(InvalidTransition):
        transition_download(DownloadStatus.FAILED, DownloadStatus.RUNNING)


def test_error_categories_cover_every_provider_failure_kind() -> None:
    for name in (
        "VALIDATION",
        "AUTHENTICATION",
        "UNAVAILABLE",
        "TIMEOUT",
        "RATE_LIMITED",
        "BUSINESS",
        "BLOCKED",
        "INTERNAL",
    ):
        assert hasattr(ErrorCategory, name)
