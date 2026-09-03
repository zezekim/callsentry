"""Import-and-mount smoke tests.

The rest of the suite exercises pure logic and never imports the route modules,
so a missing runtime dependency (or a bad router import) would sail through it
and only surface when the container actually boots. These tests import the real
application and assert the whole surface is reachable.

Routes are checked through the OpenAPI schema and real requests rather than by
walking `app.routes` - recent FastAPI keeps included routers as lazy wrapper
objects there, so introspecting that list is both version-fragile and further
from what a client actually sees.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def app():
    # Imported inside the fixture so an import failure is reported as a test
    # failure rather than a collection error.
    from callsentry.main import app as fastapi_app

    return fastapi_app


@pytest.fixture(scope="module")
def client(app):
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="module")
def schema(app):
    """Also proves every response model across the API is serialisable."""
    return app.openapi()


def test_application_imports(app):
    assert app.title == "CallSentry"


PUBLIC_ROUTES = [
    ("post", "/auth/login"),
    ("get", "/auth/me"),
    ("post", "/auth/change-password"),
    ("post", "/auth/demo"),
    ("get", "/calls"),
    ("get", "/calls/stats"),
    ("get", "/calls/export"),
    ("get", "/calls/{call_id}"),
    ("get", "/appointments"),
    ("get", "/appointments/calendar"),
    ("patch", "/appointments/{appointment_id}/status"),
    ("post", "/kb/upload"),
    ("get", "/kb/documents"),
    ("delete", "/kb/documents/{document_id}"),
    ("post", "/kb/test"),
    ("get", "/settings"),
    ("patch", "/settings"),
    ("post", "/settings/test-voice"),
    ("post", "/settings/connect-cal"),
    ("get", "/settings/providers"),
    ("get", "/settings/users"),
    ("post", "/settings/users"),
    ("put", "/settings/users/{user_id}/password"),
    ("delete", "/settings/users/{user_id}"),
    ("get", "/settings/platform"),
    ("put", "/settings/platform"),
    ("get", "/analytics"),
    ("post", "/webhooks/twilio"),
    ("post", "/webhooks/twilio/status"),
    ("post", "/webhooks/cal"),
    ("post", "/admin/businesses"),
    ("get", "/admin/businesses"),
    ("delete", "/admin/businesses/{business_id}"),
    ("get", "/admin/costs"),
    ("get", "/health"),
]


@pytest.mark.parametrize(("method", "path"), PUBLIC_ROUTES)
def test_public_route_is_documented(schema, method, path):
    assert path in schema["paths"], f"{path} is not mounted"
    assert method in schema["paths"][path], f"{method.upper()} {path} is not mounted"


def test_internal_routes_are_excluded_from_public_schema(schema):
    assert not any(path.startswith("/internal") for path in schema["paths"])


def test_health_endpoint_responds(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_protected_route_rejects_anonymous_request(client):
    # 401, not 404 - proves the route exists and the auth dependency ran.
    assert client.get("/calls").status_code == 401


@pytest.mark.parametrize("path", ["/internal/turn", "/internal/hangup"])
def test_internal_route_is_mounted_and_token_guarded(client, path):
    response = client.post(path, json={"call_id": "x", "utterance": "hi"})
    assert response.status_code == 403, "internal routes must reject an unsigned caller"


def test_internal_route_rejects_wrong_token(client):
    response = client.post(
        "/internal/turn",
        json={"call_id": "x", "utterance": "hi"},
        headers={"X-Internal-Token": "not-the-token"},
    )
    assert response.status_code == 403


def _viewer_token() -> str:
    from callsentry.core.security import issue_token

    return issue_token(
        user_id="00000000-0000-0000-0000-000000000001", business_id="b", role="viewer"
    )


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("patch", "/settings"),
        ("get", "/settings"),
        ("get", "/settings/users"),
        ("put", "/settings/platform"),
        ("post", "/kb/test"),
        ("post", "/auth/change-password"),
        ("get", "/admin/costs"),
        ("patch", "/appointments/x/status"),
    ],
)
def test_viewer_token_is_refused_before_any_route_runs(client, method, path):
    # 403 from the middleware, without touching the database.
    response = client.request(method, path, headers={"Authorization": f"Bearer {_viewer_token()}"})
    assert response.status_code == 403
    assert response.json()["detail"] == "this account is view-only"
