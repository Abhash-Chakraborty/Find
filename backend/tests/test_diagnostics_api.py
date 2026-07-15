"""API tests for GET /api/admin/diagnostics/bundle."""

from __future__ import annotations

import json
from contextlib import ExitStack
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
    "runtime": {"python_version": "3.12.0"},
    "migrations": {"status": "ok", "current": "abc", "heads": ["abc"]},
    "services": {
        "postgresql": {"ok": True, "latency_ms": 1.0},
        "redis": {"ok": True, "latency_ms": 1.0},
        "storage": {"ok": True, "backend": "minio", "latency_ms": 1.0},
    },
    "queue": {"mode": "redis", "depth": 0, "queued": 0, "started": 0, "failed": 0},
    "models": {"ml_mode": "mock", "configured_models": [], "loaded_models": []},
    "errors": [],
}

# Same placeholder fixtures as the redaction tests (non-secrets for scanners).
_EXAMPLE_PASSWORD = "EXAMPLE_PASSWORD_PLACEHOLDER"
_EXAMPLE_API_KEY = "sk-test-" + "FAKE-KEY-FOR-TESTING-ONLY"
_SEEDED_FILENAME = "vacation-photo-2024.jpg"
_SEEDED_PATH = r"C:\Users\alice\Pictures\vacation-photo-2024.jpg"
_SEEDED_TXT = "private_notes.txt"
_SEEDED_DOTFILE = ".env"


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


def _assert_no_leakage(payload) -> None:
    blob = json.dumps(payload, default=str)
    for fragment in (
        _EXAMPLE_PASSWORD,
        "FAKE-KEY-FOR-TESTING-ONLY",
        _SEEDED_FILENAME,
        _SEEDED_PATH,
        _SEEDED_TXT,
        _SEEDED_DOTFILE,
        "C:\\\\Users\\\\alice",
    ):
        assert fragment not in blob, f"fragment leaked: {fragment!r}"


def _patch_collector_with_seeded_secrets(bundle_mod):
    """Inject scrubbable secrets into collector internals for endpoint coverage."""
    stack = ExitStack()
    stack.enter_context(
        patch.object(
            bundle_mod,
            "_check_postgresql",
            return_value={"ok": True, "latency_ms": 1.0},
        )
    )
    stack.enter_context(
        patch.object(
            bundle_mod,
            "_check_redis",
            return_value={"ok": True, "latency_ms": 1.0},
        )
    )
    stack.enter_context(
        patch.object(
            bundle_mod,
            "_check_storage",
            return_value={"ok": True, "backend": "minio", "latency_ms": 1.0},
        )
    )
    stack.enter_context(
        patch.object(
            bundle_mod,
            "_collect_migration_state",
            return_value={"status": "ok", "current": "abc", "heads": ["abc"]},
        )
    )
    stack.enter_context(
        patch.object(
            bundle_mod,
            "_collect_queue_stats",
            return_value={
                "mode": "redis",
                "depth": 0,
                "queued": 0,
                "started": 0,
                "failed": 0,
            },
        )
    )
    stack.enter_context(
        patch.object(
            bundle_mod,
            "_collect_recent_errors",
            return_value=[
                {
                    "level": "ERROR",
                    "logger": "test",
                    "message": (
                        f"password={_EXAMPLE_PASSWORD} "
                        f"token={_EXAMPLE_API_KEY} "
                        f"file={_SEEDED_FILENAME} "
                        f"path={_SEEDED_PATH} "
                        f"notes={_SEEDED_TXT} "
                        f"dotenv={_SEEDED_DOTFILE}"
                    ),
                    "timestamp": "2026-07-14T00:00:00+00:00",
                    "source": "log",
                }
            ],
        )
    )
    return stack


class TestDiagnosticsBundleLocalMode:
    """conftest stubs auth as local-mode (permissive) by default."""

    def test_returns_headers_schema_and_no_leakage(self, client):
        from find_api.diagnostics import bundle as bundle_mod

        with _patch_collector_with_seeded_secrets(bundle_mod):
            resp = client.get(_ENDPOINT)

        assert resp.status_code == 200
        assert (
            resp.headers["content-disposition"]
            == 'attachment; filename="find-diagnostics-bundle.json"'
        )
        assert resp.headers["x-find-diagnostics"] == "local-only"
        body = resp.json()
        assert body["schema_version"] == 1
        assert set(body) >= {
            "schema_version",
            "generated_at",
            "privacy_notice",
            "app",
            "runtime",
            "migrations",
            "services",
            "queue",
            "models",
            "errors",
        }
        _assert_no_leakage(body)
        assert _SEEDED_TXT not in resp.text
        err_msg = body["errors"][0]["message"]
        assert _SEEDED_DOTFILE not in err_msg
        assert _EXAMPLE_PASSWORD not in err_msg

    def test_collector_failure_returns_generic_500(self, client):
        with patch(
            "find_api.routers.diagnostics.collect_diagnostics_bundle",
            side_effect=RuntimeError(
                r"boom at C:\Users\alice\secret.env with password=EXAMPLE_PASSWORD_PLACEHOLDER"
            ),
        ):
            resp = client.get(_ENDPOINT)

        assert resp.status_code == 500
        assert resp.headers["x-find-diagnostics"] == "local-only"
        assert (
            resp.headers["content-disposition"]
            == 'attachment; filename="find-diagnostics-bundle.json"'
        )
        body = resp.json()
        assert body == {"error": "Failed to generate diagnostics bundle"}
        assert "EXAMPLE_PASSWORD_PLACEHOLDER" not in resp.text
        assert "Traceback" not in resp.text
        assert "RuntimeError" not in resp.text


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
