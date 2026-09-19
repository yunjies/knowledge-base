"""Mirrors `apps/api`: the HTTP surface reachable from the checkout.

Every check here is a hard assertion. Where a module cannot be imported because
of the absent `packages.infrastructure.secrets`, the test fails and says so:
an unreachable capability is a defect, not an excused omission.
"""

from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient

ROUTE_MODULES = [
    "apps.api.routes_library",
    "apps.api.routes_phase4",
    "apps.api.routes_providers",
    "apps.api.routes_services",
    "apps.api.routes_acquisition",
    "apps.api.routes_agent",
    "apps.api.routes_automation",
    "apps.api.routes_wishlist",
    "apps.api.routes_jobs",
]

BLOCK_CAUSE = "packages.infrastructure.secrets"


def _import_or_fail(module_name: str):
    """Import a module, turning a blocked import into an explicit failure."""
    try:
        return importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        assert BLOCK_CAUSE not in str(exc), (
            f"{module_name} cannot be imported: it reaches the absent "
            f"module {BLOCK_CAUSE}. Restore that module to make this pass."
        )
        raise


def _app_or_fail():
    return _import_or_fail("apps.api.main").app


@pytest.mark.parametrize("module_name", ROUTE_MODULES)
def test_route_module_declares_a_router(module_name: str) -> None:
    """Each route module must present an importable FastAPI router."""
    assert hasattr(_import_or_fail(module_name), "router")


def test_health_endpoint_contract() -> None:
    """`/health` answers with the stable identity the compose healthchecks poll."""
    client = TestClient(_app_or_fail())
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "home-media-pilot"


def test_version_endpoint_reports_the_package_version() -> None:
    client = TestClient(_app_or_fail())
    body = client.get("/version").json()
    assert body["name"] == "home-media-pilot"
    assert body["version"]


def test_cors_defaults_to_local_development_origins(monkeypatch: pytest.MonkeyPatch) -> None:
    main = _import_or_fail("apps.api.main")
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    origins = main.configured_cors_origins()
    assert any("localhost" in origin for origin in origins)
    assert all(origin.startswith("http") for origin in origins)


def test_cors_origins_are_read_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    main = _import_or_fail("apps.api.main")
    monkeypatch.setenv("CORS_ORIGINS", "http://nas:18081, http://nas:18080 ,")
    assert main.configured_cors_origins() == ["http://nas:18081", "http://nas:18080"]


def test_exposed_routes_cover_every_documented_capability() -> None:
    """Read the assembled route table and check each documented group exists.

    The OpenAPI schema is used rather than `app.routes` because included routers
    appear there only as opaque mounts.
    """
    paths = set(_app_or_fail().openapi().get("paths", {}))
    for expected in (
        "/health",
        "/library/scan",
        "/library/status",
        "/services/status",
        "/services/qb/health",
        "/services/mteam/search",
        "/services/jellyfin/sync",
        "/acquisition/preview",
        "/acquisition/approvals",
    ):
        assert expected in paths, f"missing route: {expected}"
