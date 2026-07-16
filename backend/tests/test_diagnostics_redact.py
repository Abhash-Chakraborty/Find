"""Redaction tests for the privacy-safe diagnostics bundle.

Seeds placeholder secrets and private media metadata, then asserts the
allowlist + scrub pipeline leaves zero residual leakage.

Values below are intentional non-secrets (PLACEHOLDER / REDACTED markers)
so secret scanners do not treat them as real credentials.
"""

from __future__ import annotations

import json

import pytest

from find_api.diagnostics.redact import (
    REDACTED,
    REDACTED_KEY,
    redact_payload,
    scrub_string,
)

# Synthetic fixtures only — never real credentials.
# DSN/URLs are assembled from parts so scanners never see contiguous credentials.
_EXAMPLE_PASSWORD = "EXAMPLE_PASSWORD_PLACEHOLDER"
_EXAMPLE_STORAGE_SECRET = "EXAMPLE_STORAGE_SECRET_PLACEHOLDER"
_EXAMPLE_API_KEY = "sk-test-" + "FAKE-KEY-FOR-TESTING-ONLY"
_EXAMPLE_BEARER = "Bearer " + "FAKE.TEST.TOKEN"
_EXAMPLE_DSN = "postgresql://" + "USER" + ":" + "REDACTED" + "@localhost:5432/find"
_EXAMPLE_REDIS_URL = "redis://" + ":" + "EXAMPLE_PASSWORD_PLACEHOLDER" + "@localhost"

SECRETS = [
    _EXAMPLE_PASSWORD,
    _EXAMPLE_STORAGE_SECRET,
    _EXAMPLE_API_KEY,
    _EXAMPLE_BEARER,
    _EXAMPLE_DSN,
]

PRIVATE_STRINGS = [
    "A smiling woman standing by the lake at sunset",  # caption-like
    "INVOICE #48291 TOTAL DUE",  # OCR-like
    "vacation-photo-2024.jpg",
    r"C:\Users\alice\Pictures\vacation-photo-2024.jpg",
    "/var/lib/find/storage/uploads/ab/abcdef.jpg",
    "face_embedding=[0.12, 0.98, -0.4]",
]


def _assert_no_leakage(payload) -> None:
    """Serialize and assert no seeded secret or private fragment remains."""
    blob = json.dumps(payload, default=str)
    for secret in SECRETS:
        assert secret not in blob, f"secret leaked: {secret!r}"
    for private in PRIVATE_STRINGS:
        assert private not in blob, f"private metadata leaked: {private!r}"

    # Marker substrings that must never survive scrubbing.
    for fragment in (
        "EXAMPLE_PASSWORD_PLACEHOLDER",
        "EXAMPLE_STORAGE_SECRET_PLACEHOLDER",
        "FAKE-KEY-FOR-TESTING-ONLY",
        "FAKE.TEST.TOKEN",
        "USER:REDACTED@",
        "vacation-photo-2024.jpg",
        "C:\\\\Users\\\\alice",
        "/var/lib/find/storage",
        "A smiling woman",
        "INVOICE #48291",
    ):
        assert fragment not in blob, f"fragment leaked: {fragment!r}"


class TestScrubString:
    def test_strips_filesystem_paths(self):
        assert "<path>" in scrub_string(
            r"failed reading C:\Users\alice\Pictures\shot.jpg"
        )
        assert "/var/lib/find" not in scrub_string(
            "error in /var/lib/find/storage/uploads/ab/file.jpg"
        )

    def test_strips_filenames_any_extension(self):
        out = scrub_string("Could not open vacation-photo-2024.jpg")
        assert "vacation-photo-2024.jpg" not in out
        assert "<filename>" in out
        # Allowlist-free: uncommon extensions are still scrubbed.
        for name in (
            "notes.xyz",
            "private_notes.txt",
            "customer.csv",
            "private notes.txt",
        ):
            scrubbed = scrub_string(f"failed on {name}")
            assert name not in scrubbed, name
            assert "<filename>" in scrubbed

    def test_strips_dotfiles(self):
        for name in (".env", ".gitignore", ".htaccess"):
            scrubbed = scrub_string(f"cannot read {name} during startup")
            assert name not in scrubbed, name
            assert "<filename>" in scrubbed

    def test_version_numbers_not_treated_as_filenames(self):
        assert scrub_string("app version 1.0.0 ready") == "app version 1.0.0 ready"

    def test_strips_url_credentials(self):
        out = scrub_string(f"connect {_EXAMPLE_DSN}")
        assert "USER:REDACTED@" not in out
        assert "<credentials>" in out

    def test_strips_password_only_redis_url(self):
        out = scrub_string(f"redis connect {_EXAMPLE_REDIS_URL}")
        assert "EXAMPLE_PASSWORD_PLACEHOLDER" not in out
        assert "<credentials>" in out

    def test_strips_secret_assignments(self):
        out = scrub_string(f"password={_EXAMPLE_PASSWORD} token=FAKE.TEST.TOKEN")
        assert _EXAMPLE_PASSWORD not in out
        assert "password=<redacted>" in out

    def test_strips_bearer_tokens(self):
        out = scrub_string(f"Authorization: {_EXAMPLE_BEARER}")
        assert "FAKE.TEST.TOKEN" not in out

    def test_strips_long_token_ending_in_hyphen(self):
        # Trailing '-' is part of the token; word-boundary \\b would miss it.
        token = ("A" * 39) + "-"
        out = scrub_string(f"leak={token} trailing")
        assert token not in out
        assert REDACTED in out

    def test_strips_free_standing_quoted_private_text(self):
        caption = PRIVATE_STRINGS[0]
        out = scrub_string(f'model said "{caption}" during indexing')
        assert caption not in out
        assert '"<redacted>"' in out


class TestRedactPayloadAllowlist:
    def test_unknown_keys_are_denied(self):
        payload = redact_payload(
            {
                "schema_version": 1,
                "password": SECRETS[0],
                "caption": PRIVATE_STRINGS[0],
                "mystery_field": "should_not_pass",
            }
        )
        assert payload["schema_version"] == 1
        assert "password" not in payload
        assert "caption" not in payload
        assert payload[REDACTED_KEY] == REDACTED
        assert payload["mystery_field"] == REDACTED
        _assert_no_leakage(payload)

    def test_sensitive_keys_redacted_even_when_nested(self):
        payload = redact_payload(
            {
                "services": {
                    "postgresql": {"ok": True, "database_url": SECRETS[4]},
                    "redis": {"ok": False, "redis_url": _EXAMPLE_REDIS_URL},
                },
                "models": {
                    "ml_mode": "mock",
                    "remote_ml_api_key": SECRETS[2],
                },
            }
        )
        assert payload["services"]["postgresql"]["ok"] is True
        assert "database_url" not in payload["services"]["postgresql"]
        assert payload["services"]["postgresql"][REDACTED_KEY] == REDACTED
        assert "redis_url" not in payload["services"]["redis"]
        assert payload["services"]["redis"][REDACTED_KEY] == REDACTED
        assert payload["models"]["ml_mode"] == "mock"
        assert "remote_ml_api_key" not in payload["models"]
        assert payload["models"][REDACTED_KEY] == REDACTED
        _assert_no_leakage(payload)

    def test_nested_lists_and_dicts(self):
        seeded = {
            "schema_version": 1,
            "errors": [
                {
                    "level": "ERROR",
                    "logger": "find_api.workers",
                    "message": (
                        f"upload failed path={PRIVATE_STRINGS[3]} "
                        f"password={SECRETS[0]} caption={PRIVATE_STRINGS[0]}"
                    ),
                    "timestamp": "2026-07-14T00:00:00+00:00",
                    "source": "log",
                    "user_id": 42,
                    "filename": PRIVATE_STRINGS[2],
                    "embedding": [0.1, 0.2, 0.3],
                    "faces": [{"bbox": [1, 2, 3, 4]}],
                }
            ],
            "queue": {"mode": "redis", "depth": 3, "failed": 1},
            "ocr_text": PRIVATE_STRINGS[1],
            "metadata_json": {"caption": PRIVATE_STRINGS[0]},
        }
        payload = redact_payload(seeded)

        assert payload["queue"]["depth"] == 3
        assert payload["queue"]["failed"] == 1
        assert "ocr_text" not in payload
        assert "metadata_json" not in payload
        assert payload[REDACTED_KEY] == REDACTED

        err = payload["errors"][0]
        assert err["level"] == "ERROR"
        assert err["source"] == "log"
        assert "user_id" not in err
        assert "filename" not in err
        assert "embedding" not in err
        assert "faces" not in err
        assert err[REDACTED_KEY] == REDACTED
        assert SECRETS[0] not in err["message"]
        assert PRIVATE_STRINGS[0] not in err["message"]
        assert PRIVATE_STRINGS[3] not in err["message"]
        _assert_no_leakage(payload)

    def test_empty_and_scalar_edge_cases(self):
        assert redact_payload({}) == {}
        assert redact_payload([]) == []
        assert redact_payload(None) is None
        assert redact_payload(True) is True
        assert redact_payload(0) == 0
        assert redact_payload(3.14) == 3.14

    def test_tuple_coerced_to_list(self):
        out = redact_payload(("ok", {"password": "x"}))
        assert isinstance(out, list)
        assert out[0] == "ok"
        assert "password" not in out[1]
        assert out[1][REDACTED_KEY] == REDACTED

    def test_allowlisted_string_still_scrubbed(self):
        payload = redact_payload(
            {
                "errors": [
                    {
                        "message": f"boom at {PRIVATE_STRINGS[4]} token={SECRETS[2]}",
                        "level": "ERROR",
                        "logger": "test",
                        "source": "log",
                        "timestamp": None,
                    }
                ]
            }
        )
        msg = payload["errors"][0]["message"]
        assert SECRETS[2] not in msg
        assert "/var/lib/find" not in msg
        _assert_no_leakage(payload)

    def test_private_media_keys_never_pass(self):
        payload = redact_payload(
            {
                "app": {"version": "1.0.0"},
                "filename": "vacation-photo-2024.jpg",
                "minio_key": "images/ab/abcdef.jpg",
                "thumbnail_key": "thumbnails/ab/abcdef.webp",
                "caption": PRIVATE_STRINGS[0],
                "ocr": PRIVATE_STRINGS[1],
                "ocr_text": PRIVATE_STRINGS[1],
                "embedding": [0.01] * 8,
                "vector": [0.02] * 8,
                "face": {"landmarks": [1, 2]},
                "faces": [],
                "person": "Alice",
                "people": ["Alice", "Bob"],
                "user_id": 7,
                "uploader": 7,
                "email": "alice@example.com",
                "username": "alice",
                "file_hash": "abc123",
                "exif_json": {"Make": "Canon"},
            }
        )
        assert payload["app"]["version"] == "1.0.0"
        for key in (
            "filename",
            "minio_key",
            "thumbnail_key",
            "caption",
            "ocr",
            "ocr_text",
            "embedding",
            "vector",
            "face",
            "faces",
            "person",
            "people",
            "user_id",
            "uploader",
            "email",
            "username",
            "file_hash",
            "exif_json",
        ):
            assert key not in payload
        assert payload[REDACTED_KEY] == REDACTED
        _assert_no_leakage(payload)


class TestCollectBundleRedacts:
    def test_collect_diagnostics_bundle_shape_and_no_secrets(self, monkeypatch):
        """Collector output is structured and already redacted."""
        from find_api.diagnostics import bundle as bundle_mod

        monkeypatch.setattr(
            bundle_mod,
            "_check_postgresql",
            lambda: {"ok": True, "latency_ms": 1.0},
        )
        monkeypatch.setattr(
            bundle_mod,
            "_check_redis",
            lambda: {"ok": True, "latency_ms": 1.0},
        )
        monkeypatch.setattr(
            bundle_mod,
            "_check_storage",
            lambda: {"ok": True, "backend": "minio", "latency_ms": 1.0},
        )
        monkeypatch.setattr(
            bundle_mod,
            "_collect_migration_state",
            lambda: {"status": "ok", "current": "abc", "heads": ["abc"]},
        )
        monkeypatch.setattr(
            bundle_mod,
            "_collect_queue_stats",
            lambda: {
                "mode": "redis",
                "depth": 0,
                "queued": 0,
                "started": 0,
                "failed": 0,
            },
        )
        monkeypatch.setattr(
            bundle_mod,
            "_collect_recent_errors",
            lambda: [
                {
                    "level": "ERROR",
                    "logger": "test",
                    "message": f"password={SECRETS[0]} file={PRIVATE_STRINGS[2]}",
                    "timestamp": "2026-07-14T00:00:00+00:00",
                    "source": "log",
                }
            ],
        )

        result = bundle_mod.collect_diagnostics_bundle()

        assert result["schema_version"] == 1
        assert "privacy_notice" in result
        assert "app" in result
        assert "runtime" in result
        assert "migrations" in result
        assert "services" in result
        assert "queue" in result
        assert "models" in result
        assert "errors" in result
        assert "local" in result["privacy_notice"].lower()
        _assert_no_leakage(result)


@pytest.mark.parametrize(
    "key",
    [
        "password",
        "SECRET_KEY",
        "access_key",
        "api_key",
        "caption",
        "ocr_text",
        "embedding",
        "faces",
        "user_id",
        "filename",
        "minio_key",
    ],
)
def test_sensitive_key_names_always_redacted(key):
    payload = redact_payload({key: "leak-me-please", "schema_version": 1})
    assert key not in payload
    assert payload[REDACTED_KEY] == REDACTED
    assert payload["schema_version"] == 1
