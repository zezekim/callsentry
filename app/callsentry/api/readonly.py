"""Server-side enforcement of the viewer role.

A viewer may read the operational pages and nothing else. The rule lives in
one place and is applied as middleware from the JWT's role claim, so a new
mutating route is read-only for viewers by default rather than by remembering
to add a dependency.
"""

from __future__ import annotations

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

# Whole sections a viewer never sees, even read-only.
HIDDEN_PREFIXES = ("/settings", "/admin")

# Carve-outs inside hidden sections that the overview page needs.
VISIBLE_EXCEPTIONS = ("/settings/providers",)

# Non-GET requests that are harmless.
ALLOWED_WRITES = frozenset({"/auth/logout"})


def viewer_allowed(method: str, path: str) -> bool:
    if method.upper() not in SAFE_METHODS:
        return path in ALLOWED_WRITES
    if path.startswith(HIDDEN_PREFIXES) and not path.startswith(VISIBLE_EXCEPTIONS):
        return False
    return True
