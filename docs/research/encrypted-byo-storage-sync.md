# Research: Encrypted Bring-Your-Own-Storage Sync

- **Status:** Research complete, implementation not started
- **Date:** 2026-08-03
- **Related:** Issue #187. Builds on `docs/plans/not-started/storage-provider-neutrality-adr.md`,
  `docs/plans/partial/vault-encryption-design.md`, and the installer/model-cache direction in #45.
- **Scope:** Design comparison only. No provider integration, no hosted Find storage, no credential
  handling code, and no automatic upload is proposed for implementation here.

## Summary

Find should offer optional backup to storage the user already owns, with media encrypted on the
local machine before it leaves. The recommended v1 boundary is **a manual, encrypted, resumable
snapshot pushed to a generic S3-compatible endpoint or a local/mounted filesystem path, through a
sync target interface that is deliberately separate from the live `StorageBackend`.** Consumer
drive providers (Google Drive, Dropbox, OneDrive) are explicitly deferred, and the reasons are in
[Provider comparison](#provider-comparison).

Two findings from the current codebase shape everything below and are easy to get wrong:

1. **The provider-neutral storage abstraction has already landed.** `storage_abstract.py`,
   `storage_factory.py`, `storage_local.py`, and `storage_minio.py` exist and `storage.py` is now a
   facade over them. The ADR in `docs/plans/not-started/` still says no abstraction has landed;
   that status line is stale and should be corrected when this work starts.
2. **The vault no longer encrypts media at rest.** Per `vault-encryption-design.md`, Find 1.1.3
   keeps hidden media in the ordinary private object store behind password-gated, memory-only vault
   sessions, and migrates legacy AES-256-GCM blobs back into plain private storage after first
   unlock. The vault is currently an *access-control* boundary, not a cryptographic one.

Finding 2 is the important one. The issue's requirement that "vault blobs are encrypted locally
before upload" **cannot be satisfied by reusing what the vault does today**, because today it does
not encrypt. Sync must own its own encryption layer and treat everything it uploads as ciphertext
it produced itself. Anything else would ship exactly the false confidence the vault design note
warns against.

## Why sync is not another StorageBackend

The tempting shortcut is to add `storage_s3.py` or `storage_gdrive.py` alongside the existing
backends and call it sync. That is the wrong shape, for three reasons:

- **Different lifecycle.** `StorageBackend` is a *live, authoritative* blob store: the app reads
  through it on every gallery request and expects low latency and read-after-write. A backup target
  is written occasionally, read almost never, and may be offline for weeks.
- **Different failure semantics.** A failed `get_file` on the live backend is a broken page. A
  failed backup upload is a retry. Collapsing them means one set of error handling has to serve
  both, and the stricter one wins by accident.
- **Different content.** The live backend stores plaintext bytes. The backup target must only ever
  see ciphertext. If backup is a `StorageBackend`, every existing caller becomes a potential path
  for plaintext to reach it.

The v1 shape is therefore a separate, narrow interface — call it `SyncTarget` — with roughly
`put_object(key, stream)`, `get_object(key)`, `list_prefix(prefix)`, `delete_object(key)`, and
`capabilities()`. It is used only by an explicit sync command, never by request handlers.

## Provider comparison

Assessed on the criteria the issue asks for. "Maintenance" means ongoing cost to Find, not to the
user: SDK churn, auth flows that break, provider policy changes.

| Option | Privacy | Portability | Cost | Offline behaviour | Maintenance |
| --- | --- | --- | --- | --- | --- |
| **Local/mounted filesystem** (external drive, NAS, SMB/NFS mount) | Best — bytes never touch a network Find controls or a third party | Best — a directory tree the user can copy, inspect, `rsync` | Zero beyond the disk | Native; the target simply is or is not mounted | Lowest — `pathlib` and `os.replace`, no SDK |
| **Generic S3-compatible** (MinIO, Backblaze B2, Wasabi, Garage, Ceph, Hetzner, AWS) | Good — ciphertext only; provider sees object sizes and timing | Good — one protocol, many vendors, no lock-in | User's own bill; egress varies sharply by vendor | Poor while offline, but retry is clean and resumable | Low — one stable protocol, already a dependency via MinIO SDK |
| **Consumer drive** (Google Drive, Dropbox, OneDrive) | Weaker — OAuth means a Find-registered app identity sits in the trust path | Poor — proprietary file IDs, per-provider semantics | Free tiers exist; quota and throttling are real constraints | Poor; SDKs assume connectivity | **Highest** — OAuth client registration, consent screens, token refresh, provider review, per-provider quirks |
| **Local encrypted export** (single archive the user moves themselves) | Best — Find never speaks to a network at all | Best — one file | Zero | Perfect; it is inherently offline | Very low |

### Detailed notes

**Local/mounted filesystem** is the strongest option on every axis except convenience, and it costs
almost nothing to build because the target is a path. It also covers the NAS case, which is common
among exactly the self-hosting users Find is aimed at. It should be in v1.

**Generic S3-compatible** is the right *network* option because it is a protocol rather than a
vendor. The user picks endpoint, region, bucket, and keys; Find never learns who the provider is
and never needs a per-provider integration. The MinIO SDK already in the dependency tree speaks it,
so this adds no new dependency. It should be in v1.

**Consumer drive providers** are where this gets expensive. OAuth for Drive/Dropbox/OneDrive
requires Find to register a *client application*, which means a Find-controlled identity is
structurally in the trust path even though Find hosts no storage — a meaningful weakening of the
local-first promise, not just an engineering cost. The alternative, asking users to register their
own OAuth app, is a genuinely bad user experience. They also have the highest ongoing maintenance:
consent screens get re-reviewed, scopes get deprecated, refresh tokens expire in provider-specific
ways.

The recommendation is to satisfy this demand **indirectly**: because the v1 target is a plain
directory, users who want Drive or Dropbox can point Find at a folder that the provider's own
desktop client syncs, or at an `rclone mount`. That covers the use case in v1 with zero provider
code, and it keeps the option of a native integration open for later without committing to it now.

**Local encrypted export** is a degenerate case of the filesystem target — same code path, no
scheduling. Worth exposing as its own command because "give me one file I can put on a USB stick"
is a distinct and reasonable user request.

## Credentials: what the user supplies and where it may live

Exactly two credential sets, and they are handled very differently.

**Storage credentials.** For S3-compatible targets: endpoint URL, region, bucket, access key ID,
secret access key, and a TLS flag. For filesystem targets: a path, and nothing else.

- Supplied by the user at configuration time.
- Stored in the existing settings/env mechanism, the same way `MINIO_ACCESS_KEY` is today. They are
  deployment configuration, not user secrets.
- **Never** written into the database, the backup manifest, or any log line. The diagnostics bundle
  redaction in `backend/src/find_api/diagnostics/redact.py` is the model to copy here: it is
  allowlist-first, so an unrecognised key is denied by default rather than needing a matching deny
  rule, with explicit patterns for names like `access_key` / `secret_key` and for named URL keys
  such as `database_url` and `redis_url`. Sync logging should adopt the same posture — deny unless
  the field was deliberately allowed — rather than trying to enumerate what to hide.
- Scoped as narrowly as the provider allows — a bucket-scoped key with put/get/list/delete, never a
  root account key. This must be in the user-facing documentation.

**The backup passphrase.** This is the one genuine user secret and it is categorically different.

- Supplied interactively when the user creates or restores a backup.
- **Never persisted anywhere** — not in the database, not in settings, not in the OS keychain for
  v1. Held in process memory for the duration of the operation only, matching how vault sessions
  already work.
- Losing it means losing the backup. This is stated plainly in the UI, not buried in docs. There is
  no recovery path and Find must not pretend otherwise.

Deliberately excluded from v1: OS keychain integration, passphrase caching across runs, and any
"remember me" affordance. Each is a real convenience feature and each needs its own threat-model
review.

## Encryption design

Reuse the primitives the vault design already settled on rather than inventing a second scheme.

- **Content encryption:** AES-256-GCM, so large images are never fully resident.
  ChaCha20-Poly1305 remains an acceptable alternative on hardware without AES-NI; the vault note
  already covers this trade-off.
- **Chunk framing is mandatory, and this is the easiest thing here to get catastrophically wrong.**
  AES-GCM has no safe "streaming" mode of its own: a nonce may never repeat under a given key, and
  a partial plaintext must never be released before its tag verifies. So an object is split into
  fixed-size chunks, each encrypted as its own AEAD message with a nonce derived deterministically
  as `nonce_prefix || chunk_counter` (random 32-bit prefix per object, 64-bit counter), and each
  chunk's AAD binds the object key **and its chunk index** so chunks cannot be reordered, dropped,
  or spliced between objects. The final chunk is flagged in its AAD so truncation is detectable.
  Decryption verifies each chunk before emitting it. Resume works at chunk boundaries only, and a
  resumed upload must reuse the same nonce prefix and counter sequence — never restart the counter.
  Implementation must use a reviewed construction rather than hand-rolling this.
- **Key derivation:** Argon2id from the backup passphrase, with a per-backup random salt stored in
  the manifest. Parameters recorded in the manifest so a future parameter change stays readable.
- **Key hierarchy:** the passphrase derives a key-encryption key; a random per-backup data key is
  wrapped by it. Rotating the passphrase then rewrites one small header instead of re-encrypting
  every object.
- **Associated data:** every object's AAD binds format version, backup ID, and object key, so
  ciphertext cannot be swapped between entries by someone with write access to the bucket. This is
  the same reasoning the vault note gives for binding AAD to `media_id` and `file_hash`.
- **Encryption timing:** at the sync boundary, streaming from the live storage backend into the
  target. Plaintext is never written to a temporary file on the way out. The uploaded object is
  ciphertext from the first byte.

### What still leaks

Stating this precisely matters more than the cipher choice:

- **Object count and individual sizes.** Padding to size buckets would mitigate this at a storage
  cost. Not proposed for v1, but the manifest format should leave room for it.
- **Timing.** When backups run, and roughly how much changed.
- **The manifest**, unless it is encrypted too — it must be, since it contains object keys and
  sizes. Only a small unencrypted header (format version, KDF parameters, salt) stays readable, and
  it must contain nothing user-specific.
- **`file_hash` must not be uploaded in plaintext.** It is a SHA-256 of the raw image bytes and, as
  the vault note already says, fingerprints a known image without the blob. It belongs inside the
  encrypted manifest, never in an object key or a plaintext index.

## Sync behaviour

**Identity.** Each backup destination gets a random `backup_id` (UUIDv4) generated on first use and
recorded in the encrypted manifest. Deliberately *not* derived from hostname, user, or install ID —
those leak, and they break when a user restores onto new hardware, which is the primary reason
anyone has a backup at all.

**Object keys.** `{backup_id}/objects/{HMAC(data_key, media_uuid)}`. The HMAC means the key reveals
nothing about content or ordering while staying deterministic, so re-uploading the same media
converges instead of duplicating.

**Conflict.** v1 declares **the local library authoritative and sync one-directional**. This is the
single most important scope decision in the document. Bidirectional sync needs vector clocks or
similar causality tracking, a merge UI for genuine conflicts, and tombstone reconciliation — and
gets it wrong quietly. Two machines pointed at one destination is a *detected and refused*
condition in v1: the manifest records the writer's `backup_id`, and a second writer refuses and
tells the user, rather than interleaving.

**Retry.** Per-object, resumable, idempotent. Objects are content-addressed by their HMAC key, so a
retry either finds the object present and skips it, or re-uploads it whole. Exponential backoff
with a cap; a failed run leaves a valid older manifest in place — the manifest is written **last**,
after every object it references, so an interrupted run never produces a manifest pointing at
objects that were never uploaded.

**Deletion.** Deletions do not propagate automatically in v1. A local delete leaves the remote
object in place until an explicit prune, which is opt-in, reports what it will remove first, and
honours a configurable grace period. Silent propagating deletion turns "backup" into "mirror," and
a mirror faithfully reproduces the accident that made the user want a backup.

**Restore.** Reads the manifest, prompts for the passphrase, verifies the KDF header, then streams
objects back through the live storage backend. Restore is always explicit, never automatic, and
must be verifiable without writing anything — a `--verify` mode that walks the manifest, checks
every AEAD tag, and reports drift. A backup nobody has tested restoring is not a backup.

## Recommended v1 boundary

Ship exactly this:

1. A `SyncTarget` interface, separate from `StorageBackend`, with filesystem and S3-compatible
   implementations.
2. Manual, user-triggered backup and restore. No scheduling, no daemon, no background upload.
3. AES-256-GCM content encryption with Argon2id key derivation, applied at the sync boundary.
4. An encrypted manifest, written last, with a minimal plaintext header.
5. One-directional sync with local authoritative, and second-writer detection.
6. An explicit, opt-in prune, and a restore `--verify` mode.

Why this boundary: it delivers the actual user value — "my library survives this disk dying" —
without a Find-hosted service, without OAuth, without a background process touching user data
unattended, and without the causality problems of bidirectional sync. Every deferred item below can
be added later without changing the on-disk format, because the manifest is versioned.

## What must not be implemented yet

- Bidirectional or multi-writer sync, and any automatic conflict merging.
- Native Google Drive, Dropbox, or OneDrive integration, and any OAuth client registration.
- Scheduled or background sync, including "on idle" triggers.
- Passphrase persistence of any kind, including OS keychain storage.
- Automatic deletion propagation.
- Any Find-hosted relay, coordinator, or credential broker.
- Sharing a backup destination between users, or any multi-tenant key hierarchy.
- Size-bucket padding — noted as a known leak, deferred deliberately.

## Open questions for implementation

1. Does the backup include derived data — thumbnails, embeddings, captions — or only originals plus
   the database rows needed to rebuild them? Originals-only is smaller and more portable;
   including derived data makes restore dramatically faster on large libraries. Needs a measured
   answer, and the model-cache direction in #45 is relevant since restore may otherwise require
   re-downloading model weights before the library is usable again.
2. Argon2id parameters for a *backup* passphrase, where a multi-second derivation is acceptable and
   should probably be much higher than an interactive login would tolerate.
3. Whether the encrypted manifest needs chunking for very large libraries, or whether a single
   object is adequate to a realistic ceiling.

## References

- `docs/plans/not-started/storage-provider-neutrality-adr.md` — provider-neutral direction; its
  "current implementation status" is stale as described above
- `docs/plans/partial/vault-encryption-design.md` — threat model, cipher and KDF rationale, AAD
  requirement, and the current no-encryption-at-rest status
- `backend/src/find_api/core/storage_abstract.py` — the live backend contract this must not reuse
- `backend/src/find_api/diagnostics/redact.py` — deny-by-default redaction, a good model for what
  sync logging must never emit
