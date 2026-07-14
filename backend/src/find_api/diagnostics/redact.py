"""Allowlist-first redaction for diagnostics payloads.

Sensitive user and deployment data must never leave a diagnostics bundle.
Unknown keys are denied by default; only explicitly allowlisted keys keep
their values, and every string value is still pattern-scrubbed.
"""

from __future__ import annotations

import re
from typing import Any

REDACTED = "[REDACTED]"
REDACTED_KEY = "redacted_key"

# Keys whose values may appear in a diagnostics bundle after scrubbing.
# Deny-by-default: anything not listed is replaced with REDACTED.
ALLOWED_KEYS: frozenset[str] = frozenset(
    {
        # Top-level / meta
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
        # App / runtime
        "version",
        "environment",
        "python_version",
        "python_implementation",
        "platform",
        "platform_release",
        "platform_machine",
        # Migrations
        "current",
        "heads",
        "status",
        "detail",
        # Service health
        "postgresql",
        "redis",
        "storage",
        "ok",
        "latency_ms",
        "error",
        "backend",
        "reachable",
        # Queue
        "mode",
        "depth",
        "queued",
        "started",
        "failed",
        "finished",
        "deferred",
        "scheduled",
        # Models / providers (names and modes only — never weights or URLs)
        "ml_mode",
        "accel_mode",
        "clip_model",
        "clip_pretrained",
        "blip_model",
        "yolo_model",
        "use_gpu",
        "embedding_dim",
        "configured_models",
        "loaded_models",
        "remote_ml_configured",
        "queue_mode",
        "storage_backend",
        # Error log entries (messages already scrubbed)
        "level",
        "logger",
        "message",
        "timestamp",
        "source",
        "count",
        # Placeholder used when a sensitive key name is itself redacted
        REDACTED_KEY,
    }
)

# Key names that are always stripped even if somehow allowlisted.
_SENSITIVE_KEY_RE = re.compile(
    r"(?i)^(password|passwd|secret|token|api[_-]?key|access[_-]?key|"
    r"secret[_-]?key|authorization|auth|credential|credentials|"
    r"session|cookie|bearer|private[_-]?key|minio_key|thumbnail_key|"
    r"filename|filepath|file_path|path|object_name|caption|ocr|"
    r"ocr_text|embedding|vector|face|faces|person|people|"
    r"user(_?id)?|uploader|email|username|display_name|"
    r"database_url|redis_url|remote_ml_url|remote_ml_api_key|"
    r"metadata_json|exif_json|file_hash)$"
)

# Substring matches for nested private media/metadata keys.
_SENSITIVE_KEY_SUBSTRING_RE = re.compile(
    r"(?i)(password|passwd|secret|token|api[_-]?key|access[_-]?key|"
    r"secret[_-]?key|authorization|credential|caption|ocr|embedding|"
    r"vector|face|filename|filepath|file_path|minio_key|thumbnail_key|"
    r"user_id|uploader|database_url|redis_url)"
)

# Filesystem paths (Windows drive + Unix absolute).
# Avoid matching URL schemes like postgresql:// (drive letter + '//').
_PATH_RE = re.compile(
    r"(?:"
    r"[a-zA-Z]:(?:\\+|/(?!/))(?:[\w\-. ]+[\\/]+)*[\w\-. ]+"
    r"|"
    r"(?<![A-Za-z0-9+.-])/(?:[\w\-. ]+/)+[\w\-. ]+"
    r")"
)

# Filename-like tokens: basename + '.' + extension starting with a letter.
# Digit-only suffixes (e.g. version fragments like 1.0) are not filenames.
_FILENAME_RE = re.compile(r"(?i)\b[\w\-]+\.[A-Za-z][A-Za-z0-9]{0,15}\b")

# Credentials embedded in URLs / DSNs: scheme://user:pass@host
# username may be empty (redis://:password@host).
_URL_CREDS_RE = re.compile(
    r"([a-z][a-z0-9+.-]*://)[^:\s/]*:[^@\s/]+@",
    re.IGNORECASE,
)

# Bearer / raw token-looking strings.
_BEARER_RE = re.compile(
    r"(?i)\bbearer\s+[A-Za-z0-9\-._~+/]+=*",
)
_TOKEN_RE = re.compile(
    r"(?i)\b(?:sk-[a-z0-9]{10,}|"
    r"[a-f0-9]{32,}|[A-Za-z0-9_\-]{40,})\b",
)

# password=..., token: ..., SECRET_KEY=... style assignments.
_SECRET_ASSIGN_RE = re.compile(
    r"(?i)\b(password|passwd|secret|token|api[_-]?key|access[_-]?key|"
    r"secret[_-]?key|authorization)\s*[=:]\s*\S+",
)

# Private media metadata leaked into free-text log lines (keyed assignments).
_PRIVATE_FIELD_ASSIGN_RE = re.compile(
    r"(?i)\b(caption|ocr(?:_text)?|embedding|vector|face(?:s)?|"
    r"person|people|filename|filepath|file_path|minio_key|"
    r"user(?:_?id)?|uploader|email|username)\s*[=:]\s*.+?(?=(?:\s+\w+=)|$)",
)

# Free-standing quoted strings that may embed caption/OCR text without a prefix.
_QUOTED_CONTENT_RE = re.compile(r"""(['"])([^'"\n]{8,})\1""")


def _is_sensitive_key(key: str) -> bool:
    if _SENSITIVE_KEY_RE.match(key):
        return True
    return bool(_SENSITIVE_KEY_SUBSTRING_RE.search(key))


def scrub_string(value: str) -> str:
    """Remove paths, filenames, credentials, and token-like substrings."""
    msg = _URL_CREDS_RE.sub(r"\1<credentials>@", value)
    msg = _BEARER_RE.sub(f"Bearer {REDACTED}", msg)
    msg = _SECRET_ASSIGN_RE.sub(r"\1=<redacted>", msg)
    msg = _PRIVATE_FIELD_ASSIGN_RE.sub(r"\1=<redacted>", msg)
    msg = _QUOTED_CONTENT_RE.sub(r"\1<redacted>\1", msg)
    msg = _TOKEN_RE.sub(REDACTED, msg)
    msg = _PATH_RE.sub("<path>", msg)
    msg = _FILENAME_RE.sub("<filename>", msg)
    return msg


def redact_payload(data: Any) -> Any:
    """Recursively redact a diagnostics payload using allowlist + scrubbing.

    - Sensitive dict keys are renamed to ``redacted_key`` (value ``[REDACTED]``)
      so the original key name does not leak.
    - Other dict keys not on the allowlist keep their name but get
      ``[REDACTED]`` values.
    - Strings under allowlisted keys are still pattern-scrubbed.
    - Lists and nested dicts are walked recursively.
    """
    if isinstance(data, dict):
        out: dict[str, Any] = {}
        for key, value in data.items():
            key_str = str(key)
            if _is_sensitive_key(key_str):
                out[REDACTED_KEY] = REDACTED
                continue
            if key_str not in ALLOWED_KEYS:
                out[key_str] = REDACTED
                continue
            out[key_str] = redact_payload(value)
        return out

    if isinstance(data, list):
        return [redact_payload(item) for item in data]

    if isinstance(data, tuple):
        return [redact_payload(item) for item in data]

    if isinstance(data, str):
        return scrub_string(data)

    # bool/int/float/None and other primitives pass through unchanged.
    return data
