"""Mirrors `packages/infrastructure/config`: settings, redaction, secret hygiene."""

from __future__ import annotations

import pytest

from packages.infrastructure.config.redaction import redact


def test_magnet_links_are_redacted() -> None:
    assert redact("magnet:?xt=urn:btih:deadbeef") == "[REDACTED]"


@pytest.mark.parametrize(
    "key",
    [
        "api_key",
        "authorization",
        "cookie",
        "credential",
        "password",
        "private_key",
        "secret",
        "token",
    ],
)
def test_sensitive_keys_are_redacted_at_any_depth(key: str) -> None:
    assert redact({key: "value"})[key] == "[REDACTED]"
    assert redact({"outer": {"inner": {key: "value"}}})["outer"]["inner"][key] == (
        "[REDACTED]"
    )


def test_non_sensitive_values_survive_redaction() -> None:
    payload = {"title": "Dune", "size_bytes": 1024, "nested": {"year": 2021}}
    assert redact(payload) == payload


def test_redaction_walks_lists() -> None:
    result = redact({"items": [{"token": "x"}, {"title": "ok"}]})
    assert result["items"][0]["token"] == "[REDACTED]"
    assert result["items"][1]["title"] == "ok"


def test_settings_parse_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    from packages.infrastructure.config.settings import AppSettings

    monkeypatch.setenv("APP_ENV", "test-env")
    monkeypatch.setenv("APP_LOG_LEVEL", "DEBUG")
    settings = AppSettings.from_environment()
    assert settings.environment == "test-env"
    assert settings.log_level == "DEBUG"


def test_logical_roots_read_json_and_legacy_env(monkeypatch: pytest.MonkeyPatch) -> None:
    from packages.infrastructure.library.roots import configured_roots

    roots = configured_roots(
        {
            "LOGICAL_PATHS": '{"电影": "/media/电影", "动漫": "/media/动漫"}',
            "MOVIES_ROOT": "/legacy/movies",
        }
    )
    assert roots["电影"].as_posix() == "/media/电影"
    assert roots["动漫"].as_posix() == "/media/动漫"
    assert roots["movies"].as_posix() == "/legacy/movies"


def test_invalid_logical_paths_json_is_rejected() -> None:
    from packages.infrastructure.library.roots import configured_roots

    with pytest.raises(ValueError):
        configured_roots({"LOGICAL_PATHS": "{not json"})
    with pytest.raises(ValueError):
        configured_roots({"LOGICAL_PATHS": '["a list, not an object"]'})
