"""Mirrors `packages/contracts`: validation rules at the API boundary."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from packages.contracts.acquisition import AcquisitionPreviewRequest
from packages.contracts.media_libraries import (
    MediaLibraryCreateRequest,
    ProviderConfigUpdateRequest,
)
from packages.contracts.providers import MetadataSearchRequest, SubtitleSearchRequest


def test_media_library_requires_at_least_one_path() -> None:
    with pytest.raises(ValidationError):
        MediaLibraryCreateRequest(
            name="电影", paths=[], metadata_provider="tvmaze", subtitle_provider="opensubtitles"
        )


def test_media_library_rejects_a_blank_name() -> None:
    with pytest.raises(ValidationError):
        MediaLibraryCreateRequest(
            name="",
            paths=["电影"],
            metadata_provider="tvmaze",
            subtitle_provider="opensubtitles",
        )


def test_media_library_defaults_to_enabled() -> None:
    request = MediaLibraryCreateRequest(
        name="电影", paths=["电影"], metadata_provider="tvmaze", subtitle_provider="opensubtitles"
    )
    assert request.enabled is True


def test_provider_update_accepts_partial_payloads() -> None:
    assert ProviderConfigUpdateRequest().model_dump(exclude_none=True) == {}
    assert ProviderConfigUpdateRequest(enabled=False).enabled is False


def test_acquisition_preview_requires_source_identity() -> None:
    with pytest.raises(ValidationError):
        AcquisitionPreviewRequest(
            source="", external_id="1", title="x", category="c", save_path="/p"
        )


def test_metadata_search_request_carries_optional_episode_identity() -> None:
    request = MetadataSearchRequest(
        query="Severance", media_type="series", year=2022, season=2, episode=3
    )
    assert (request.season, request.episode) == (2, 3)


def test_subtitle_search_request_accepts_a_title_only_query() -> None:
    request = SubtitleSearchRequest(query="Dune")
    assert request.query == "Dune"
    assert request.year is None
