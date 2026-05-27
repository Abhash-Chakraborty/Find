# Vault Encryption Design Note

- **Status:** Partially complete
- **Date:** 2026-05-21
- **Last reviewed:** 2026-05-28
- **Related:** Issue #183
- **Current implementation status:** Vault unlock, hide, list, lock, and stream flows exist with encrypted blob storage and tests. The implementation does not fully match this design note yet: it uses AES-GCM instead of the documented ChaCha20-Poly1305 decision, does not bind AEAD associated data to `media_id`/`file_hash`, and should be reviewed against the metadata/vector exclusion requirements before this plan is marked complete.

## Problem

Before building the Hidden Images vault, the project needs a documented encryption design and
threat model. Bad encryption architecture is worse than no vault because it gives users false
confidence.

## Threat model

### What the vault protects against

- A third party who gains read access to the object store (MinIO bucket, filesystem blob directory)
  cannot view vault images without the user's passphrase.
- A process that reads the PostgreSQL/SQLite database cannot reconstruct vault image content from
  stored metadata alone.

### What the vault does not protect against

- An attacker who has already compromised the running API process or worker process (keys are
  in-process memory while the vault is unlocked).
- The user's own operating system or a process running with equal or higher privilege than the API.
- Metadata fields that remain plaintext by design (see Encryption boundary below). `file_hash` in
  particular is a SHA-256 of the raw image bytes and is always stored in the database; it can
  fingerprint a known image even without the blob.
- Brute-force attacks against a weak passphrase. The KDF raises the cost but cannot compensate for
  a trivially guessable passphrase.
- Physical access to a running, unlocked device.

## Cipher comparison: AES-256-GCM vs ChaCha20-Poly1305

Both are authenticated encryption with associated data (AEAD) constructions. Either is acceptable
for this use case. The differences relevant to Find are:

**Required associated data (AAD):**

Every vault blob encryption operation must supply AAD that binds the ciphertext to its database
record and format. At minimum, the AAD must be the exact byte serialization of:

- a fixed format/version string, for example `find-vault-v1`
- `media_id`
- `file_hash`

This AAD is not encrypted, but it is authenticated by the AEAD tag. Decryption must reconstruct
the identical AAD from trusted metadata and must reject the blob if authentication fails. This
prevents an attacker with write access to the blob store from swapping encrypted blobs between
records and having them still verify successfully.

| Property | AES-256-GCM | ChaCha20-Poly1305 |
| --- | --- | --- |
| Hardware acceleration | Excellent on modern x86-64 with AES-NI | Not needed; fast in pure software |
| Timing safety | Requires AES-NI; software fallback can leak timing | Constant-time in software by design |
| Standard support | NIST, TLS 1.3, very widely deployed | RFC 8439, TLS 1.3, growing deployment |
| Python availability | `cryptography` library, no extra dependency | `cryptography` library, no extra dependency |
| Nonce length | 96-bit (12 bytes) | 96-bit (12 bytes) |
| Authentication tag | 128-bit | 128-bit |

**Decision: ChaCha20-Poly1305.**

Find targets a local-first desktop app running on end-user hardware. Hardware AES acceleration is
not guaranteed across all supported machines. ChaCha20-Poly1305 is constant-time in software,
which removes a whole class of timing-side-channel risk without requiring anything beyond the
`cryptography` package already usable in the backend.

## Key derivation

The vault derives an encryption key from the user's passphrase using **Argon2id**.

Argon2id is the recommended KDF from the OWASP Password Storage Cheat Sheet (2024) for cases
where both GPU resistance and side-channel resistance are needed. It combines the data-independent
memory access pattern of Argon2i (side-channel resistant) with the data-dependent pattern of
Argon2d (GPU resistant).

### Recommended baseline parameters

| Parameter | Value | Notes |
| --- | --- | --- |
| `time_cost` (iterations) | 2 | OWASP 2024 minimum baseline |
| `memory_cost` | 19456 KiB (19 MiB) | OWASP 2024 minimum baseline |
| `parallelism` | 1 | Safe single-threaded default |
| `hash_len` | 32 bytes | Matches ChaCha20-Poly1305 key length |
| `salt` | 16 bytes, random per vault | Must be stored alongside the encrypted blob or in a vault metadata record |

Parameters should be tunable via `config.py` (`VAULT_ARGON2_TIME_COST`, `VAULT_ARGON2_MEMORY_COST`,
`VAULT_ARGON2_PARALLELISM`) so operators can raise them as hardware improves without code changes.

The derived key is **never written to disk or to the database**. It lives only in API process
memory for the duration of an unlock session.

## Encryption boundary

### What is encrypted

- The raw image bytes (the blob stored in MinIO or the local filesystem).
- Each blob is encrypted independently with a fresh random 96-bit nonce.
- The stored format per file is: `nonce (12 bytes) || ciphertext || tag (16 bytes)`.
- AEAD **must** also authenticate Associated Data (AAD) that is not stored inside the
  ciphertext, so that a valid encrypted blob cannot be swapped onto a different media record.
- The AAD for each blob must be the exact UTF-8 string:
  `vault:v1|media_id:<id>|file_hash:<file_hash>`
  — `vault:v1` is a format/version marker; `media_id` binds the blob to its database record;
  `file_hash` binds it to the expected plaintext fingerprint already stored for duplicate
  detection.
- Decryption **must** reconstruct the same AAD from the current record and pass it to the
  AEAD decrypt call. If any component differs (wrong record, tampered metadata), authentication
  fails and the blob must be rejected.

### What stays plaintext in the database

| Field | Reason |
| --- | --- |
| `id` | Internal primary key; no content revealed |
| `file_hash` | Required for duplicate detection; reveals fingerprint of content (known limitation, documented in threat model) |
| `filename` | Needed for display; consider hashing or omitting if filename is sensitive |
| `status` | Required for job pipeline |
| `is_hidden` | New flag that marks a media record as vault-protected |
| `created_at`, `updated_at` | Timestamps; reveal when the image was added but not what it contains |
| `file_size` | Minor content signal; acceptable tradeoff for storage management |

### What is excluded from ML and search

- **`vector`** (embedding): Must be `NULL` for vault images. CLIP/SigLIP embeddings encode visual
  semantics; a stored embedding defeats the vault's privacy guarantee even without the blob.
- **`metadata_json`** (caption, objects, OCR text): Must not be populated for vault images. AI
  captions and detected objects are human-readable descriptions of image content.
- **`exif_json`**: Should not be extracted for vault images. EXIF may contain GPS coordinates,
  device identifiers, or timestamps.
- **`cluster_id`**: Vault images must not participate in clustering. Cluster membership leaks
  visual similarity across the vault boundary.

The analyze_image worker job must check the `is_hidden` flag and skip all ML processing for vault
images. The gallery and search endpoints must exclude vault images unless the vault is unlocked
for the current session.

## Unlock session model

This is a high-level design only. Implementation details belong in a follow-up issue.

1. The user provides their passphrase via a dedicated vault unlock endpoint.
2. The API derives the vault key from the passphrase + stored salt using Argon2id.
3. The derived key is stored only in server memory in an entry keyed by a vault session token
   and bound to the authenticated user. Do **not** store the key in a process-global variable
   (cross-user key exposure risk) and do not rely on request-scoped context for key persistence
   across requests.
4. While the vault is unlocked, requests that present the vault session token look up that
   session-specific in-memory key and use it to decrypt and serve vault image blobs.
5. Each vault session entry must have explicit expiry semantics (idle timeout and/or absolute TTL).
   Lock, logout, expiry, and process restart must all zero and discard the in-memory key. No key
   material is ever persisted to disk or database.
6. Vault sessions do not survive a process restart; users must unlock again after a restart.

Exact token format, TTL policy, distributed-cache design, and other implementation details are
out of scope for this research note.

## Risks

| Risk | Severity | Notes |
| --- | --- | --- |
| `file_hash` fingerprinting | Medium | Known and accepted; see threat model |
| Nonce reuse | High | Each encryption must generate a fresh random nonce; never reuse a nonce with the same key |
| Key logging | High | Upload, download, and decryption paths must never log key material or nonces |
| `MINIO_PUBLIC_READ=true` | Low | Encrypted blobs served via public URL are still opaque ciphertext; acceptable but should be documented for operators |
| Weak passphrase | Medium | KDF raises cost; cannot substitute for a strong passphrase |
| In-memory key lifetime | Medium | Key is cleared on lock, but lives in memory while unlocked; OS memory inspection is out of scope |

## What changes are needed (not in scope here)

This note is research only. A follow-up implementation issue should cover:

- `Media` model: add `is_hidden` boolean column.
- `workers/jobs.py`: skip ML processing when `is_hidden` is true.
- `routers/gallery.py` and `routers/search.py` (if it exists): filter vault images out of results
  unless unlocked.
- New vault router: unlock endpoint, lock endpoint, serve decrypted blob.
- `core/config.py`: add `VAULT_ARGON2_*` parameters.
- Alembic migration for the `is_hidden` column.
- Unit tests for the vault key derivation helper (no real images needed; mock bytes suffice).

## Decision

- **Cipher:** ChaCha20-Poly1305
- **KDF:** Argon2id with OWASP 2024 baseline parameters
- **Key lifetime:** In-memory only; never persisted
- **Encryption scope:** Raw image blobs only; all ML-derived fields (`vector`, `metadata_json`,
  `exif_json`, `cluster_id`) are excluded for vault images
- **No recovery path:** A forgotten passphrase cannot be recovered. This must be communicated
  clearly in the UI before the user creates a vault.

## References

- OWASP Password Storage Cheat Sheet (2024): https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html
- RFC 8439 – ChaCha20 and Poly1305: https://www.rfc-editor.org/rfc/rfc8439
- Python `cryptography` library: https://cryptography.io/en/latest/hazmat/primitives/aead/
- Argon2 reference implementation: https://github.com/P-H-C/phc-winner-argon2
- Related codebase files reviewed:
  - `backend/src/find_api/models/media.py`
  - `backend/src/find_api/core/storage.py`
  - `backend/src/find_api/core/config.py`
  - `backend/src/find_api/routers/gallery.py`
  - `docs/plans/partial/local-first-roadmap.md`
  - `docs/plans/not-started/storage-provider-neutrality-adr.md`
