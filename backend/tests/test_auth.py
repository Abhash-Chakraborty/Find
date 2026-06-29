"""End-to-end tests for the backend authentication system.

Covers setup, login/logout, invite generation, join requests, and
admin approval / rejection workflows.  All tests use the shared
in-memory SQLite client from conftest.py and require no external
services.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _use_real_auth_dependencies(client):
    """Exercise the real auth dependencies in this module.

    conftest's shared client fixture forces local-mode auth (None) so that
    pre-auth tests keep working. The auth tests need the genuine
    get_required_user / get_admin_user behavior, so remove those overrides
    here and restore them afterwards. Depends on ``client`` so it runs after
    the shared fixture has installed its overrides.
    """
    from find_api.core.dependencies import get_admin_user, get_required_user
    from find_api.main import app

    removed = {}
    for dep in (get_required_user, get_admin_user):
        if dep in app.dependency_overrides:
            removed[dep] = app.dependency_overrides.pop(dep)
    yield
    app.dependency_overrides.update(removed)


@pytest.fixture(autouse=True, scope="module")
def _disable_rate_limit():
    """Disable SlowAPI rate limiting for all auth tests.

    Tests share a single in-process client IP so the 5/minute login
    limit fires mid-suite if not disabled.
    """
    import find_api.routers.auth as auth_module

    auth_module.limiter.enabled = False
    yield
    auth_module.limiter.enabled = True


# ---------------------------------------------------------------------------
# Helper callables
# ---------------------------------------------------------------------------

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "s3cure!pass"
ADMIN_DISPLAY = "Server Admin"

WRONG_PASSWORD = "wrongpassword123"


def _setup_admin(client, username=ADMIN_USERNAME, password=ADMIN_PASSWORD):
    resp = client.post(
        "/api/auth/setup",
        json={
            "username": username,
            "password": password,
            "display_name": ADMIN_DISPLAY,
        },
    )
    assert resp.status_code == 200, f"Admin setup failed: {resp.text}"
    data = resp.json()
    assert "token" in data, f"Token missing from setup response: {data}"
    assert "user" in data, f"User missing from setup response: {data}"
    return data


def _login(client, username=ADMIN_USERNAME, password=ADMIN_PASSWORD):
    return client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _create_invite(client, token: str):
    resp = client.post("/api/auth/invites", headers=_auth_header(token))
    assert resp.status_code == 200, f"Invite creation failed: {resp.text}"
    data = resp.json()
    assert "invite_token" in data, f"invite_token missing: {data}"
    return data


def _join(client, invite_token: str, username="newuser", password="newpass123"):
    resp = client.post(
        "/api/auth/join",
        json={
            "invite_token": invite_token,
            "username": username,
            "password": password,
            "display_name": "New Member",
        },
    )
    assert resp.status_code == 200, f"Join request failed: {resp.text}"
    data = resp.json()
    assert "join_request_id" in data, f"join_request_id missing: {data}"
    return data


# ---------------------------------------------------------------------------
# Instance setup
# ---------------------------------------------------------------------------


class TestSetup:
    def test_setup_creates_admin(self, client):
        data = _setup_admin(client)
        assert data["user"]["username"] == ADMIN_USERNAME
        assert data["user"]["role"] == "admin"
        assert "token" in data
        assert "expires_at" in data

    def test_setup_only_once(self, client):
        _setup_admin(client)
        resp = client.post(
            "/api/auth/setup",
            json={"username": "second", "password": "password123"},
        )
        assert resp.status_code == 409

    def test_setup_enforces_min_password_length(self, client):
        resp = client.post(
            "/api/auth/setup",
            json={"username": "admin", "password": "short"},
        )
        assert resp.status_code == 422

    def test_setup_rejects_password_over_72_bytes(self, client):
        long_password = "a" * 73
        resp = client.post(
            "/api/auth/setup",
            json={"username": "admin", "password": long_password},
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Login / logout
# ---------------------------------------------------------------------------


class TestLogin:
    def test_login_returns_token(self, client):
        _setup_admin(client)
        resp = _login(client)
        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data
        assert data["user"]["username"] == ADMIN_USERNAME

    def test_login_updates_last_login(self, client, db):
        _setup_admin(client)
        from find_api.models.user import User

        before = db.query(User).filter(User.username == ADMIN_USERNAME).first()
        last_login_before = before.last_login if before else None

        _login(client)

        db.expire_all()
        after = db.query(User).filter(User.username == ADMIN_USERNAME).first()
        assert after is not None
        assert after.last_login is not None
        if last_login_before is not None:
            assert after.last_login >= last_login_before

    def test_login_rejects_bad_password(self, client):
        _setup_admin(client)
        resp = _login(client, password=WRONG_PASSWORD)
        assert resp.status_code == 401

    def test_login_rejects_unknown_user(self, client):
        _setup_admin(client)
        resp = _login(client, username="ghost")
        assert resp.status_code == 401

    def test_login_error_bodies_are_indistinguishable(self, client):
        """Bad-password and unknown-user must return the same error body.

        Identical responses prevent user-enumeration via the login endpoint.
        """
        _setup_admin(client)
        bad_pass_resp = _login(client, password=WRONG_PASSWORD)
        unknown_user_resp = _login(client, username="ghost")
        assert bad_pass_resp.status_code == unknown_user_resp.status_code == 401
        assert bad_pass_resp.json() == unknown_user_resp.json()

    def test_token_works_on_me_endpoint(self, client):
        data = _setup_admin(client)
        token = data["token"]
        resp = client.get("/api/auth/me", headers=_auth_header(token))
        assert resp.status_code == 200
        assert resp.json()["user"]["username"] == ADMIN_USERNAME

    def test_me_returns_local_mode_without_token(self, client):
        resp = client.get("/api/auth/me")
        assert resp.status_code == 200
        body = resp.json()
        assert body["mode"] == "local"
        assert body["user"] is None

    def test_logout_invalidates_token(self, client):
        data = _setup_admin(client)
        token = data["token"]
        headers = _auth_header(token)

        logout = client.post("/api/auth/logout", headers=headers)
        assert logout.status_code == 200

        me = client.get("/api/auth/me", headers=headers)
        # In shared mode the token no longer resolves → 401
        assert me.status_code == 401


# ---------------------------------------------------------------------------
# Invite tokens
# ---------------------------------------------------------------------------


class TestInvites:
    def test_admin_can_create_invite(self, client):
        data = _setup_admin(client)
        inv = _create_invite(client, data["token"])
        assert "invite_token" in inv
        assert "expires_at" in inv
        assert "id" in inv

    def test_non_admin_cannot_create_invite(self, client):
        resp = client.post("/api/auth/invites")
        # local mode → 400 (not in shared mode)
        assert resp.status_code in (400, 401, 403)

    def test_invite_appears_in_list(self, client):
        data = _setup_admin(client)
        token = data["token"]
        _create_invite(client, token)

        resp = client.get("/api/auth/invites", headers=_auth_header(token))
        assert resp.status_code == 200
        assert len(resp.json()["invites"]) == 1

    def test_invite_is_single_use(self, client):
        data = _setup_admin(client)
        token = data["token"]
        inv = _create_invite(client, token)
        invite_token = inv["invite_token"]

        # First use should succeed
        _join(client, invite_token)

        # Second use must fail
        resp = client.post(
            "/api/auth/join",
            json={
                "invite_token": invite_token,
                "username": "another",
                "password": "pass12345",
            },
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Join requests
# ---------------------------------------------------------------------------


class TestJoinRequests:
    def test_join_requires_valid_invite(self, client):
        _setup_admin(client)
        resp = client.post(
            "/api/auth/join",
            json={
                "invite_token": "invalid_token",
                "username": "newuser",
                "password": "newpass123",
            },
        )
        assert resp.status_code == 400

    def test_join_creates_pending_request(self, client):
        data = _setup_admin(client)
        inv = _create_invite(client, data["token"])
        join_data = _join(client, inv["invite_token"])
        assert join_data["status"] == "pending"

    def test_join_rejects_duplicate_username(self, client):
        data = _setup_admin(client)
        token = data["token"]

        inv1 = _create_invite(client, token)
        _join(client, inv1["invite_token"], username="newuser")

        inv2 = _create_invite(client, token)
        resp = client.post(
            "/api/auth/join",
            json={
                "invite_token": inv2["invite_token"],
                "username": "newuser",
                "password": "newpass123",
            },
        )
        assert resp.status_code == 409

    def test_join_rejects_password_over_72_bytes(self, client):
        data = _setup_admin(client)
        inv = _create_invite(client, data["token"])
        resp = client.post(
            "/api/auth/join",
            json={
                "invite_token": inv["invite_token"],
                "username": "newuser",
                "password": "a" * 73,
            },
        )
        assert resp.status_code == 422

    def test_approve_creates_user_account(self, client):
        data = _setup_admin(client)
        token = data["token"]
        inv = _create_invite(client, token)
        join_data = _join(client, inv["invite_token"])
        req_id = join_data["join_request_id"]

        resp = client.post(
            f"/api/auth/join-requests/{req_id}/approve",
            headers=_auth_header(token),
        )
        assert resp.status_code == 200
        assert resp.json()["user"]["username"] == "newuser"
        assert resp.json()["user"]["role"] == "member"

    def test_approved_user_can_login(self, client):
        data = _setup_admin(client)
        token = data["token"]
        inv = _create_invite(client, token)
        join_data = _join(client, inv["invite_token"])
        req_id = join_data["join_request_id"]

        client.post(
            f"/api/auth/join-requests/{req_id}/approve",
            headers=_auth_header(token),
        )

        login_resp = _login(client, username="newuser", password="newpass123")
        assert login_resp.status_code == 200

    def test_reject_marks_request_as_rejected(self, client):
        data = _setup_admin(client)
        token = data["token"]
        inv = _create_invite(client, token)
        join_data = _join(client, inv["invite_token"])
        req_id = join_data["join_request_id"]

        resp = client.post(
            f"/api/auth/join-requests/{req_id}/reject",
            headers=_auth_header(token),
        )
        assert resp.status_code == 200

        # Verify persistence: the request must actually be "rejected" in the DB
        list_resp = client.get("/api/auth/join-requests", headers=_auth_header(token))
        assert list_resp.status_code == 200
        requests = list_resp.json()["requests"]
        matching = [r for r in requests if r["id"] == req_id]
        assert len(matching) == 1
        assert matching[0]["status"] == "rejected"

    def test_cannot_approve_already_rejected_request(self, client):
        data = _setup_admin(client)
        token = data["token"]
        inv = _create_invite(client, token)
        join_data = _join(client, inv["invite_token"])
        req_id = join_data["join_request_id"]

        client.post(
            f"/api/auth/join-requests/{req_id}/reject",
            headers=_auth_header(token),
        )
        resp = client.post(
            f"/api/auth/join-requests/{req_id}/approve",
            headers=_auth_header(token),
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Security properties
# ---------------------------------------------------------------------------


class TestSecurityProperties:
    def test_password_is_stored_as_bcrypt_hash(self, client, db):
        _setup_admin(client)
        from find_api.models.user import User

        user = db.query(User).filter(User.username == ADMIN_USERNAME).first()
        assert user is not None
        # bcrypt hashes start with $2 (covers $2a$, $2b$, $2y$ variants)
        assert user.password_hash.startswith("$2")

    def test_unauthenticated_cannot_list_join_requests(self, client):
        _setup_admin(client)
        resp = client.get("/api/auth/join-requests")
        assert resp.status_code in (401, 403)

    def test_unauthenticated_cannot_approve_join_request(self, client):
        resp = client.post("/api/auth/join-requests/1/approve")
        assert resp.status_code in (400, 401, 403)

    def test_member_cannot_approve_join_request(self, client):
        data = _setup_admin(client)
        token = data["token"]

        inv = _create_invite(client, token)
        join_data = _join(client, inv["invite_token"])
        req_id = join_data["join_request_id"]
        client.post(
            f"/api/auth/join-requests/{req_id}/approve",
            headers=_auth_header(token),
        )

        member_login = _login(client, username="newuser", password="newpass123")
        member_token = member_login.json()["token"]

        # Create another invite so there's a pending request to try approving
        inv2 = _create_invite(client, token)
        join2 = _join(
            client, inv2["invite_token"], username="third", password="pass12345"
        )
        req2_id = join2["join_request_id"]

        resp = client.post(
            f"/api/auth/join-requests/{req2_id}/approve",
            headers=_auth_header(member_token),
        )
        assert resp.status_code == 403
