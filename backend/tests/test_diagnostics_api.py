"""API tests for GET /api/admin/diagnostics/bundle."""

from __future__ import annotations

import json
import time
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


class TestHealthProbeTimeoutIsEnforced:
    """The probe timeout must bound wall-clock time, not just raise late.

    ``with ThreadPoolExecutor(...)`` calls ``shutdown(wait=True)`` on exit, so
    the original helper blocked until the hung probe finished and the timeout
    had no effect. These assert the bound is real.
    """

    def test_returns_promptly_when_the_probe_hangs(self):
        from find_api.diagnostics.bundle import _run_with_timeout

        started = time.perf_counter()
        with pytest.raises(TimeoutError):
            _run_with_timeout(lambda: time.sleep(30), timeout_s=0.2)
        elapsed = time.perf_counter() - started

        # Generous ceiling for slow CI, still far below the 30s hang.
        assert elapsed < 5, f"timeout did not bound wall clock: {elapsed:.2f}s"

    def test_returns_value_when_the_probe_completes(self):
        from find_api.diagnostics.bundle import _run_with_timeout

        assert _run_with_timeout(lambda: "healthy", timeout_s=5) == "healthy"

    def test_propagates_probe_exceptions_unchanged(self):
        from find_api.diagnostics.bundle import _run_with_timeout

        def _boom():
            raise ValueError("probe exploded")

        with pytest.raises(ValueError, match="probe exploded"):
            _run_with_timeout(_boom, timeout_s=5)


class TestUnmockedBundleOverTheWire:
    """Exercise the real collector through the real endpoint.

    Every other endpoint test patches ``collect_diagnostics_bundle``, so none
    of them prove a genuine bundle survives strict JSON serialisation or that
    the redaction layer leaves the reported fields intact end to end.
    """

    def test_real_bundle_serialises_and_keeps_useful_fields(self, client):
        from find_api.diagnostics import bundle as bundle_mod

        # Stub only the outbound probes so the test stays fast and offline.
        # Model collection, redaction, and serialisation all run for real —
        # those are the paths no other endpoint test covers.
        with ExitStack() as stack:
            for name, value in (
                ("_check_postgresql", {"ok": True, "latency_ms": 1.0}),
                ("_check_redis", {"ok": True, "latency_ms": 1.0}),
                (
                    "_check_storage",
                    {"ok": True, "backend": "minio", "latency_ms": 1.0},
                ),
                (
                    "_collect_migration_state",
                    {"status": "ok", "current": "abc", "heads": ["abc"]},
                ),
            ):
                stack.enter_context(patch.object(bundle_mod, name, return_value=value))
            resp = client.get(_ENDPOINT)

        assert resp.status_code == 200
        body = resp.json()

        # Strict: no default=str fallback, so a stray datetime fails loudly.
        json.dumps(body)

        assert body["schema_version"] == 1
        assert set(body) >= {
            "app",
            "runtime",
            "migrations",
            "services",
            "queue",
            "models",
            "errors",
        }
        # Model identifiers must stay readable — a filename-shaped name like
        # yolo26n.pt previously collapsed to "<filename>".
        assert body["models"]["yolo_model"].endswith(".pt")
        assert isinstance(body["models"]["embedding_dim"], int)
        assert isinstance(body["errors"], list)
        _assert_no_leakage(body)
