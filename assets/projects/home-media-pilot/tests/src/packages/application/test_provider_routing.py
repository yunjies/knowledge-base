"""Mirrors `packages/application/providers`: routing, retry, and platform catalog."""

from __future__ import annotations

import pytest

from packages.frameworks.errors import ProviderError
from packages.application.provider_retry import retry_provider_call
from packages.application.provider_routing import ProviderRouter
from packages.contracts.providers import MediaLibraryConfig
from packages.domain.states import ErrorCategory
from packages.frameworks.providers import ProviderRegistry, ProviderType


class _Provider:
    def __init__(self, provider_id: str) -> None:
        self.provider_id = provider_id


class _Registry:
    def __init__(self, providers: dict[str, _Provider]) -> None:
        self._providers = providers

    def get(self, provider_id: str) -> _Provider:
        try:
            return self._providers[provider_id]
        except KeyError as exc:
            raise KeyError(f"unregistered provider: {provider_id}") from exc

    def register(self, provider: _Provider) -> None:
        self._providers[provider.provider_id] = provider


def _router(libraries: dict[str, MediaLibraryConfig]) -> ProviderRouter:
    return ProviderRouter(
        _Registry({"tvmaze": _Provider("tvmaze")}),
        _Registry({"opensubtitles": _Provider("opensubtitles")}),
        libraries,
    )


def test_path_resolves_to_the_library_that_declares_it() -> None:
    router = _router(
        {
            "电影": MediaLibraryConfig(
                paths=["电影"], metadata_provider="tvmaze", subtitle_provider="opensubtitles"
            ),
            "动漫": MediaLibraryConfig(
                paths=["动漫", "特摄"], metadata_provider="tvmaze", subtitle_provider="opensubtitles"
            ),
        }
    )
    assert router.library_for_path("特摄") == "动漫"
    assert router.metadata_for_path("电影").provider_id == "tvmaze"


def test_a_path_claimed_by_two_libraries_is_rejected_at_construction() -> None:
    with pytest.raises(ValueError):
        _router(
            {
                "a": MediaLibraryConfig(
                    paths=["shared"], metadata_provider="tvmaze", subtitle_provider="opensubtitles"
                ),
                "b": MediaLibraryConfig(
                    paths=["shared"], metadata_provider="tvmaze", subtitle_provider="opensubtitles"
                ),
            }
        )


def test_unconfigured_path_is_rejected() -> None:
    router = _router(
        {
            "电影": MediaLibraryConfig(
                paths=["电影"], metadata_provider="tvmaze", subtitle_provider="opensubtitles"
            )
        }
    )
    with pytest.raises(KeyError):
        router.library_for_path("电视剧")


def test_unregistered_provider_is_rejected_at_construction() -> None:
    with pytest.raises(KeyError):
        _router(
            {
                "电影": MediaLibraryConfig(
                    paths=["电影"], metadata_provider="missing", subtitle_provider="opensubtitles"
                )
            }
        )


def test_transient_errors_are_retried_up_to_the_bound() -> None:
    attempts = {"n": 0}

    def flaky() -> str:
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise ProviderError("p", ErrorCategory.TIMEOUT, "slow")
        return "ok"

    assert retry_provider_call(flaky, max_attempts=3) == "ok"
    assert attempts["n"] == 3


def test_retryable_error_is_reraised_after_exhausting_attempts() -> None:
    attempts = {"n": 0}

    def always_unavailable() -> str:
        attempts["n"] += 1
        raise ProviderError("p", ErrorCategory.UNAVAILABLE, "down")

    with pytest.raises(ProviderError):
        retry_provider_call(always_unavailable, max_attempts=2)
    assert attempts["n"] == 2


@pytest.mark.parametrize(
    "category",
    [ErrorCategory.BUSINESS, ErrorCategory.AUTHENTICATION, ErrorCategory.RATE_LIMITED],
)
def test_non_transient_errors_are_never_retried(category: ErrorCategory) -> None:
    attempts = {"n": 0}

    def failing() -> str:
        attempts["n"] += 1
        raise ProviderError("p", category, "no retry")

    with pytest.raises(ProviderError):
        retry_provider_call(failing, max_attempts=5)
    assert attempts["n"] == 1, f"{category} must surface immediately"


def test_zero_attempts_is_rejected() -> None:
    with pytest.raises(ValueError):
        retry_provider_call(lambda: "ok", max_attempts=0)


def test_builtin_provider_catalog_covers_every_required_kind() -> None:
    definitions = {d.provider_id: d for d in ProviderRegistry().definitions()}
    assert set(definitions) >= {
        "nas",
        "jellyfin",
        "mteam",
        "qbittorrent",
        "tvmaze",
        "metatube",
        "opensubtitles",
    }
    assert definitions["nas"].provider_type is ProviderType.STORAGE
    assert definitions["jellyfin"].provider_type is ProviderType.PLAYER
    assert definitions["mteam"].provider_type is ProviderType.RESOURCE
    assert definitions["qbittorrent"].provider_type is ProviderType.DOWNLOADER


def test_mutation_is_disabled_for_every_builtin_provider() -> None:
    """No builtin provider may advertise mutation while its adapter is read-only."""
    mutating = [
        d.provider_id for d in ProviderRegistry().definitions() if d.mutation_enabled
    ]
    assert mutating == [], f"builtin providers advertise mutation: {mutating}"


def test_duplicate_provider_id_is_rejected() -> None:
    from packages.frameworks.providers import ProviderDefinition

    registry = ProviderRegistry()
    duplicate = ProviderDefinition(
        provider_id="nas",
        provider_type=ProviderType.STORAGE,
        display_name="dup",
        description="dup",
        capabilities=(),
    )
    with pytest.raises(ValueError):
        registry._load([duplicate])
