"""Mirrors `packages/application/automation` and `scheduler` policy surfaces."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from packages.application.automation import AutomationPolicyService
from packages.application.scheduler import next_run_after
from packages.contracts.automation import AutomationPolicy


def _policy(**overrides: object) -> AutomationPolicy:
    values: dict[str, object] = {"enabled": True}
    values.update(overrides)
    return AutomationPolicy(**values)


def test_disabled_automation_blocks_every_action() -> None:
    result = AutomationPolicyService(_policy(enabled=False)).evaluate(
        site="mteam", action="auto_download"
    )
    assert result.status == "blocked"
    assert result.code == "automation_disabled"
    assert result.audit["side_effect_executed"] is False


def test_global_stop_blocks_before_any_other_rule() -> None:
    service = AutomationPolicyService(
        _policy(global_stop=True, auto_download=True, dry_run=False)
    )
    result = service.evaluate(site="mteam", action="auto_download")
    assert result.status == "blocked"
    assert result.code == "global_stop"


def test_site_stop_blocks_only_that_site() -> None:
    service = AutomationPolicyService(
        _policy(auto_download=True, stopped_sites=["mteam"], dry_run=False)
    )
    assert service.evaluate(site="mteam", action="auto_download").code == "site_stop"
    assert service.evaluate(site="other", action="auto_download").status == "allowed"


def test_action_must_be_explicitly_enabled() -> None:
    service = AutomationPolicyService(_policy(dry_run=False))
    result = service.evaluate(site="mteam", action="auto_download")
    assert result.status == "blocked"
    assert result.code == "action_disabled"


def test_download_count_limit_blocks_further_downloads() -> None:
    service = AutomationPolicyService(
        _policy(auto_download=True, max_downloads_per_run=2, dry_run=False)
    )
    assert service.evaluate(site="s", action="auto_download", downloads_in_run=1).status == (
        "allowed"
    )
    blocked = service.evaluate(site="s", action="auto_download", downloads_in_run=2)
    assert blocked.code == "download_limit"


def test_size_limit_blocks_oversized_release() -> None:
    service = AutomationPolicyService(
        _policy(auto_download=True, max_download_size_bytes=100, dry_run=False)
    )
    assert service.evaluate(site="s", action="auto_download", size_bytes=101).code == (
        "size_limit"
    )
    assert service.evaluate(site="s", action="auto_download", size_bytes=100).status == (
        "allowed"
    )


def test_dry_run_never_reports_allowed() -> None:
    service = AutomationPolicyService(_policy(auto_download=True, dry_run=True))
    result = service.evaluate(site="s", action="auto_download")
    assert result.status == "dry_run"
    assert result.code == "dry_run"


def test_evaluation_never_executes_a_side_effect() -> None:
    service = AutomationPolicyService(_policy(auto_download=True, dry_run=False))
    result = service.evaluate(site="s", action="auto_download")
    assert result.status == "allowed"
    assert result.audit["side_effect_executed"] is False


def test_hourly_and_daily_schedules_advance_one_period() -> None:
    now = datetime(2026, 1, 1, 10, 30, tzinfo=UTC)
    assert next_run_after("@hourly", now) == datetime(2026, 1, 1, 11, 0, tzinfo=UTC)
    assert next_run_after("@daily", now) == datetime(2026, 1, 2, 0, 0, tzinfo=UTC)


def test_interval_schedule_rounds_up_to_the_next_slot() -> None:
    now = datetime(2026, 1, 1, 10, 7, tzinfo=UTC)
    assert next_run_after("*/15 * * * *", now) == datetime(2026, 1, 1, 10, 15, tzinfo=UTC)


def test_interval_schedule_that_crosses_the_hour_rolls_over() -> None:
    now = datetime(2026, 1, 1, 10, 50, tzinfo=UTC)
    assert next_run_after("*/15 * * * *", now) == datetime(2026, 1, 1, 11, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    "expression",
    ["@weekly", "0 3 * * *", "*/0 * * * *", "*/61 * * * *", "*/x * * * *", "bad"],
)
def test_unsupported_schedules_are_rejected(expression: str) -> None:
    with pytest.raises(ValueError):
        next_run_after(expression, datetime(2026, 1, 1, tzinfo=UTC))
