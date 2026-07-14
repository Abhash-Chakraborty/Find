"""API tests for GET /api/admin/diagnostics/bundle."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from find_api.core.auth import create_session, hash_password
from find_api.main import app
from find_api.models.user import User

_ENDPOINT = "/api/admin/diagnostics/bundle"
_FAKE_BUNDLE = {
    "schema_version": 1,
    "privacy_notice": "Local diagnostics only.",
    "app": {"version": "1.0.0", "environment": "local"},
}


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _make_user(db, username: str, role: str) -> User:
    user = User(
        username=username,
        display_name=username,
        password_hash=hash_password("EXAMPLE_PASSWORD_PLACEHOLDER"),
        role=role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


class TestDiagnosticsBundleLocalMode:
    """conftest stubs auth as local-mode (permissive) by default."""

    def test_returns_headers_and_schema_version(self, client):
        with patch(
            "find_api.routers.diagnostics.collect_diagnostics_bundle",
            return_value=_FAKE_BUNDLE,
        ):
            resp = client.get(_ENDPOINT)

        assert resp.status_code == 200
        assert (
            resp.headers["content-disposition"]
            == 'attachment; filename="find-diagnostics-bundle.json"'
        )
        assert resp.headers["x-find-diagnostics"] == "local-only"
        body = resp.json()
        assert body["schema_version"] == 1

    def test_collector_failure_returns_sanitized_500(self, client):
        with patch(
            "find_api.routers.diagnostics.collect_diagnostics_bundle",
            side_effect=RuntimeError(
                r"boom at C:\Users\alice\secret.env with password=EXAMPLE_PASSWORD_PLACEHOLDER"
            ),
        ):
            resp = client.get(_ENDPOINT)

        assert resp.status_code == 500
        assert resp.headers["x-find-diagnostics"] == "local-only"
        body = resp.json()
        assert "error" in body
        assert "EXAMPLE_PASSWORD_PLACEHOLDER" not in body["error"]
        assert "Traceback" not in body["error"]
        assert "C:\\Users\\alice" not in body["error"]


class TestDiagnosticsBundleSharedModeAuth:
    """Admin-only enforcement once shared mode is active."""

    @pytest.fixture(autouse=True)
    def _use_real_auth_dependencies(self, client):
        from find_api.core.dependencies import get_admin_user, get_required_user

        removed = {}
        for dep in (get_required_user, get_admin_user):
            if dep in app.dependency_overrides:
                removed[dep] = app.dependency_overrides.pop(dep)
        yield
        app.dependency_overrides.update(removed)

    @pytest.fixture()
    def shared_tokens(self, db):
        admin = _make_user(db, "admin", "admin")
        member = _make_user(db, "member", "member")
        admin_token, _ = create_session(db, admin.id)
        member_token, _ = create_session(db, member.id)
        return {"admin": admin_token, "member": member_token}

    def test_unauthenticated_returns_401(self, client, shared_tokens):
        with patch(
            "find_api.routers.diagnostics.collect_diagnostics_bundle",
            return_value=_FAKE_BUNDLE,
        ):
            resp = client.get(_ENDPOINT)
        assert resp.status_code == 401

    def test_member_returns_403(self, client, shared_tokens):
        with patch(
            "find_api.routers.diagnostics.collect_diagnostics_bundle",
            return_value=_FAKE_BUNDLE,
        ):
            resp = client.get(_ENDPOINT, headers=_auth(shared_tokens["member"]))
        assert resp.status_code == 403

    def test_admin_returns_200_with_headers(self, client, shared_tokens):
        with patch(
            "find_api.routers.diagnostics.collect_diagnostics_bundle",
            return_value=_FAKE_BUNDLE,
        ):
            resp = client.get(_ENDPOINT, headers=_auth(shared_tokens["admin"]))

        assert resp.status_code == 200
        assert (
            resp.headers["content-disposition"]
            == 'attachment; filename="find-diagnostics-bundle.json"'
        )
        assert resp.headers["x-find-diagnostics"] == "local-only"
        assert resp.json()["schema_version"] == 1
