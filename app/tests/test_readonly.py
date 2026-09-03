from __future__ import annotations

import pytest

from callsentry.api.readonly import viewer_allowed


@pytest.mark.parametrize(
    ("method", "path", "allowed"),
    [
        ("GET", "/calls", True),
        ("GET", "/calls/export", True),
        ("GET", "/analytics", True),
        ("GET", "/settings/providers", True),
        ("GET", "/settings", False),
        ("GET", "/settings/platform", False),
        ("GET", "/admin/businesses", False),
        ("POST", "/kb/upload", False),
        ("DELETE", "/kb/documents/x", False),
        ("PATCH", "/appointments/x/status", False),
        ("POST", "/auth/change-password", False),
        ("POST", "/auth/logout", True),
    ],
)
def test_viewer_allowed(method, path, allowed):
    assert viewer_allowed(method, path) is allowed
