# Privacy-Safe BYOK Inference Plugin Boundary

**Status:** Design proposal — no implementation authorised by this document
**Last reviewed:** 2026-08-22
**Issue:** #353
**Related:** #260 (self-hosted remote ML mode, shipped), #261 (remote acceleration UI), `docs/policies/agent-security.md`

Find fails closed for remote inference today. This document designs the boundary
that a future bring-your-own-key option would have to sit behind, so that adding
one provider cannot quietly turn Find into a cloud upload path.

Nothing here authorises a provider SDK, a hosted API call, a credential UI, or
telemetry. The threat model and test strategy below are entry conditions for any
adapter, not follow-up work.

---

## 1. What already exists, and why it is not BYOK

`ML_MODE=remote` (#260) ships today:

- One endpoint, `REMOTE_ML_URL`; one bearer token, `REMOTE_ML_API_KEY`.
- Capability gating via `REMOTE_ML_FEATURES` (`embed,caption,detect,ocr,cluster`),
  enforced in `workers/processors.py` — the enabled list is sent to the server so
  switching `ocr` off actually stops the OCR, rather than only hiding the result.
- `REMOTE_ML_STRIP_EXIF`, defaulting on, re-encoding to JPEG before transmission.
- A validator requiring `https://` for any non-local host, because the request
  carries both photo bytes and the token.

That is a **self-hosted** path: the operator runs a Find ML server and is on both
ends of the connection. The security question is "is the pipe safe" — which TLS
plus a bearer token answers.

BYOK is a different question. The operator is on one end and a third party is on
the other, running software the operator did not build, under terms the operator
did not write, and with retention behaviour the operator cannot inspect. "Is the
pipe safe" is no longer the interesting part. The interesting part is **what
leaves, to whom, under what consent, and what happens to it afterwards.**

The distinction matters concretely:

| | Self-hosted (`ML_MODE=remote`) | Third-party BYOK |
|---|---|---|
| Who runs the model | The operator | A vendor |
| Trust basis | Operator controls both ends | Contractual, unverifiable at runtime |
| Data retention | Operator's own policy | Vendor policy, may include training use |
| Scope of a key leak | Operator's own server | Billable third-party account |
| Consent granularity | One instance-wide switch | Must be per provider, per capability |
| Correct default | Off | Off, and harder to turn on |

**A BYOK provider must never be configurable through the `REMOTE_ML_*`
settings.** Reusing them would collapse the two trust models into one switch,
and an operator who enabled self-hosted acceleration once would silently satisfy
the precondition for third-party upload.

---

## 2. Capability contract

Core jobs must not know that providers exist. `workers/processors.py` already
dispatches by stage; the boundary is a resolver returning something that
satisfies a capability protocol, with the local implementation as the default.

Capabilities are exactly the existing stages — BYOK adds no new ones:

| Capability | Input | Output | Sensitivity |
|---|---|---|---|
| `embed_image` | Image bytes | Float vector | Whole image leaves |
| `embed_text` | Query string | Float vector | **Every search the user types leaves** |
| `caption` | Image bytes | Free text | Whole image leaves |
| `ocr` | Image bytes | Text + boxes | Whole image; often the most sensitive text a library holds |
| `detect` | Image bytes | Labels + boxes | Whole image leaves |
| `cluster` | Vectors | Group assignments | No pixels, but face vectors are biometric |

Two of these deserve to be called out rather than treated as line items:

- **`embed_text` leaks intent, continuously.** Every query becomes a third-party
  log line. It is the only capability whose traffic is proportional to *usage*
  rather than to *library size*, and the only one that reveals what the user was
  looking for rather than what they own. It must be independently consentable and
  must default off even when image capabilities are on.
- **`cluster` is biometric.** Face embeddings are personal data under GDPR
  Article 9 and BIPA regardless of the absence of pixels. "No image leaves" is
  not a sufficient argument for sending them.

The protocol surface stays deliberately small — a manifest, a capability check, a
per-capability invoke, and a health probe. Anything provider-specific (auth
style, request shape, retries, response mapping) belongs inside the adapter.
`processors.py` must remain readable without knowing which provider is active.

---

## 3. Provider manifest

Declarative, versioned, reviewed in-tree. An adapter without a manifest does not
load.

```toml
[provider]
id = "example-vision"          # stable, lowercase, used as the settings key
display_name = "Example Vision"
adapter = "find_api.ml.providers.example_vision:ExampleVisionAdapter"
manifest_version = 1

[provider.endpoints]
allowed_hosts = ["api.example-vision.com"]   # exact hosts; no wildcards
require_tls = true

[provider.capabilities]
caption = { payload = "image", max_bytes = 4_194_304 }
ocr     = { payload = "image", max_bytes = 4_194_304 }
# embed_text absent => this provider cannot receive queries, and no runtime
# consent can grant it.

[provider.limits]
requests_per_minute = 60
timeout_seconds = 30
max_retries = 2

[provider.disclosure]
terms_url = "https://example-vision.com/terms"
retention = "documented"     # documented | unknown | trains-on-input
region = "us"
```

Three properties do the work:

1. **The manifest bounds the adapter.** `allowed_hosts` is enforced by the egress
   layer, not by the adapter's own HTTP calls. An adapter that tries to reach an
   undeclared host fails at the transport, so a compromised or careless adapter
   cannot exfiltrate to an arbitrary destination.
2. **Capabilities are allowlisted, not denylisted.** An absent capability cannot
   be enabled at runtime by any configuration or consent record.
3. **`retention = "trains-on-input"` is surfaced verbatim in the consent UI.** A
   provider that trains on submitted images is a materially different decision
   from one that does not, and the user makes it, not us.

---

## 4. Consent

Consent is stored per `(provider_id, capability)`. There is no instance-wide
"enable BYOK" switch, because such a switch is exactly the implicit upload path
this issue exists to prevent.

A consent record captures the provider, the capability, who granted it, when,
the manifest version and hash it was granted against, and the disclosure text
actually shown.

Rules:

1. **Deny by default.** No record means no call. An unreadable or corrupt consent
   store means no call.
2. **Consent is specific.** Granting `caption` grants nothing else. Granting for
   one provider grants nothing for another.
3. **Consent is invalidated by manifest change.** If the manifest hash changes —
   a new host, a widened capability, a changed retention claim — every record for
   that provider is void and must be re-granted. Otherwise a manifest edit
   silently broadens what the user agreed to.
4. **Consent is revocable, and revocation is immediate.** Revoking stops the next
   job; it does not wait for a restart or a queue drain.
5. **Consent does not survive a restore.** Backup restores and instance clones do
   not carry consent records, because the person restoring may not be the person
   who granted.

---

## 5. Secret handling

BYOK keys are third-party billable credentials. Treated as at least as sensitive
as the vault passphrase.

- **At rest:** encrypted with AES-256-GCM. `core/crypto.py` already provides the
  primitives used by the vault; the BYOK key set uses its own derived key with
  its own associated data, so a vault compromise does not hand over provider
  credentials, and vice versa.
- **Alternative boundary:** a secret-file path or an OS keychain reference, for
  operators who prefer credentials never enter the database. The manifest does
  not care which is used.
- **In memory:** decrypted only inside the adapter call, never cached on a
  long-lived object, never attached to a job payload, and never carried into a
  Redis/RQ queue entry — a queued job stores a provider id, never a key.
- **Never returned.** No API response includes a key, in any form, including
  masked or truncated. The API exposes only "configured" or "not configured"
  plus a last-four suffix for disambiguation.
- **Never logged.** Adapters are forbidden from logging request headers.
  Structured errors are constructed from status codes and provider error codes,
  never from raw responses — the same rule already applied in
  `core/model_footprint.py`, which logs the exception server-side and returns a
  constant placeholder.
- **Rotation:** replacing a key does not clear consent (the grant is about the
  provider and capability, not the credential). Rotation is logged. A key that
  fails auth twice is marked stale and the provider is disabled until the
  operator intervenes, so a revoked key does not produce an indefinite retry
  loop against a third-party endpoint.

---

## 6. Egress control

The egress layer is the single choke point through which any provider call
passes.

- **Host allowlist** from the manifest, checked against the resolved connection
  target. Redirects are not followed — a 3xx from a provider is an error, since
  following one would leave the allowlist behind.
- **TLS required.** No `http://` exception for third-party providers; the
  localhost carve-out in `validate_remote_ml_config` exists because a local
  server is not a network hop, which cannot be true of a vendor.
- **Timeouts** from the manifest, applied to connect and read separately.
- **Rate limits** per provider, enforced locally so a runaway job cannot generate
  an unbounded bill.
- **Redaction before transmission.** EXIF stripped (as `REMOTE_ML_STRIP_EXIF`
  already does), GPS removed, filenames and paths never sent — a filename alone
  routinely carries a name, a date, or a location.
- **Audit log,** append-only: timestamp, provider, capability, media id, byte
  count, outcome, latency. It records *that* something left and *how much*, never
  the content. Without it, "what did this provider receive?" is unanswerable, and
  that question follows every third-party incident.

---

## 7. Fail closed

The local implementation is the default for every capability. When a provider is
unavailable, unconfigured, rate-limited, or returns an error, the job:

1. Records the provider failure in the stage status.
2. Falls back to the local implementation **only if the operator explicitly
   enabled fallback for that capability.**
3. Otherwise marks the stage failed and moves on.

Fallback is opt-in rather than automatic on purpose. An operator who chose a
provider for quality may prefer a visible failure to a silent downgrade — and an
operator who chose it for speed may want the opposite. Guessing is worse than
asking once.

The inverse — falling back *to* a provider when local inference fails — is
forbidden. That is precisely the implicit upload path this boundary prevents.

---

## 8. Threat model

| # | Threat | Mitigation |
|---|---|---|
| T1 | Malicious/compromised adapter exfiltrates images | Manifest host allowlist enforced at egress, not in the adapter; no redirects |
| T2 | Manifest widened in an update, silently broadening consent | Consent bound to manifest hash; change voids all records for that provider |
| T3 | Key leaks via API response | Keys never serialised into any response; "configured" boolean plus last-four only |
| T4 | Key leaks via logs or an error report | Header logging forbidden; errors built from codes; `diagnostics/bundle.py` scrubbers extended to the BYOK key space |
| T5 | Search queries leak continuously | `embed_text` is a separate capability, defaults off, consented independently |
| T6 | Face embeddings sent to a third party | `cluster` treated as biometric; separate consent; disclosure states this explicitly |
| T7 | Runaway cost from a queue backlog | Per-provider local rate limit and max retries from the manifest |
| T8 | Silent upload after a local failure | Provider-as-fallback forbidden by design |
| T9 | Consent inherited by a restored backup or clone | Consent records excluded from backup/restore |
| T10 | Provider returns a hostile payload (oversized, malformed, injected) | Response size cap; schema validation before use; provider text never interpolated into a prompt or a shell |
| T11 | Operator cannot answer "what was sent?" after an incident | Append-only audit log of metadata for every call |
| T12 | Downgrade to plaintext by a manifest edit | `require_tls` cannot be disabled for a non-local host; enforced at egress |

---

## 9. Test strategy

Entry conditions. No adapter merges without all of these, and the first four are
the ones that would actually catch a regression that matters.

**Deny by default**
- No consent record → no outbound request. Asserted by an egress spy, not by
  inspecting a return value.
- Corrupt or unreadable consent store → no outbound request.
- Capability absent from the manifest → cannot be enabled by any config path.

**Consent lifecycle**
- Manifest hash change voids existing records; the next call is blocked until
  re-grant.
- Revocation takes effect on the next job with no restart.
- Per-capability isolation: granting `caption` leaves `ocr` and `embed_text`
  blocked.

**Secret containment**
- No API response contains the key. Asserted by serialising every BYOK-touching
  response and searching for a sentinel value — the pattern already used by
  `test_unresolvable_identifier_does_not_leak_exception_text`.
- The sentinel does not appear in captured logs, in a diagnostics bundle, or in a
  queued job payload.

**Egress**
- A request to an undeclared host fails at the transport, including when the
  adapter is deliberately written to attempt it.
- A 3xx redirect is an error, not a followed hop.
- `http://` to a non-local host is rejected.
- Timeout and rate limit are enforced from the manifest, not from adapter code.

**Fail closed**
- Provider down, unauthorised, and rate-limited each mark the stage failed
  without local fallback unless fallback was explicitly enabled.
- Local failure never escalates to a provider call.

**Redaction**
- EXIF and GPS absent from the transmitted payload.
- Filenames and paths absent.

**Audit**
- Every outbound call produces exactly one audit entry.
- The entry contains no image bytes and no key material.

A mock provider fixture — declared in-tree, never reaching a network — carries
this suite. Real provider calls do not belong in CI, for the same reason the OCR
inference tests sit behind `importorskip`.

---

## 10. Non-goals

No provider SDK, no hosted API call, no telemetry, no credential UI, and no
adapter ships under this document. The deliverable is the boundary.

## 11. Open questions for the maintainer

1. **Is BYOK wanted at all?** A local-first, privacy-focused tool can reasonably
   answer no. This design makes the option safe to build; it does not argue that
   it should be built. Self-hosted remote (#260) already covers "my laptop is too
   slow" without any third-party trust.
2. **Multi-user instances (#263).** Whose consent counts when several people
   share an instance? Per-user consent conflicts with a shared worker pool that
   processes any user's media. The simplest defensible answer is admin-only
   configuration plus a visible instance-wide disclosure — but it needs deciding
   before any adapter, not after.
3. **Where does the encryption key live?** Reusing the vault master key ties BYOK
   availability to an unlocked vault. A separate key needs its own unlock story.
4. **Does the audit log need retention limits?** It grows per processed image.
