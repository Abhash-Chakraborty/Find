# Signed Desktop Installer Release Pipeline

**Status:** Design approved for the Windows path; signing is not yet provisioned
**Last reviewed:** 2026-08-22
**Issue:** #48
**Implements:** `.github/workflows/desktop-installer.yml`

This document defines how Find produces trustworthy desktop installers, and
where the boundary sits between what a contributor can run and what only a
maintainer can run. It covers Windows concretely. macOS and Linux are described
as extension points only — nothing here claims either has been verified.

---

## Why a separate workflow

`ci.yml` validates source. `publish.yml` builds and pushes container images on a
tag. Neither touches the Tauri bundle, so today the only way to learn that
`frontend/src-tauri/` no longer builds is for someone to run `pnpm desktop:build`
by hand.

The desktop path also has a property the container path does not: the artifact is
a file a user downloads and executes on their own machine. That makes signing —
and the custody of the key that does it — the central design problem rather than
an afterthought.

---

## Trust boundary

| | `unsigned-build` | `signed-release` |
|---|---|---|
| Trigger | `pull_request` on desktop paths | `workflow_dispatch` with `sign: true` |
| Who can start it | Any contributor, including forks | Maintainers with access to the environment |
| Token permissions | `contents: read` | `contents: write` |
| Environment | none | `desktop-release` |
| Secrets reachable | none | certificate + password |
| Output | Build artifact, 14-day retention | Draft release + checksums, 30-day artifact |

The enforcement is GitHub's environment model, not a conditional. Secrets scoped
to an environment are not available to `pull_request` runs from forks at all, so
the contributor path cannot reach the signing material even if the workflow file
were edited in the pull request that runs it. A conditional alone would not give
that guarantee, because a fork controls the workflow file on its own branch.

`desktop-release` must be configured with:

- **Required reviewers** — at least one maintainer approves each signed run.
- **Deployment branch/tag rule** — restrict to `canary`, `main`, and `v*` tags so
  a signed build cannot be produced from an arbitrary branch.

---

## Certificate storage and handling

Two secrets on the `desktop-release` environment:

| Secret | Contents |
|---|---|
| `WINDOWS_CERTIFICATE` | Base64 of the `.pfx` (certificate + private key) |
| `WINDOWS_CERTIFICATE_PASSWORD` | Password protecting that `.pfx` |

Handling rules the workflow already implements:

1. The `.pfx` is materialised into `$RUNNER_TEMP`, imported into
   `Cert:\CurrentUser\My`, and the file is deleted in the same step. It is never
   written into the workspace, so it cannot be picked up by an artifact upload.
2. Signing happens through the certificate store by thumbprint. The password
   never appears on a command line, and therefore never in a log.
3. Nothing echoes either secret. GitHub's log masking is treated as a backstop,
   not as the control.

### Enabling signing

The workflow is deliberately inert until someone completes these steps — a
`signed-release` run fails its preflight rather than emitting an unsigned file:

1. Obtain an OV or EV code-signing certificate. EV (hardware-backed) removes the
   SmartScreen reputation warm-up but cannot be exported as a `.pfx`; see the
   HSM note below.
2. Add both secrets to the `desktop-release` environment.
3. Add the thumbprint to `frontend/src-tauri/tauri.conf.json`:

   ```json
   "bundle": {
     "windows": {
       "certificateThumbprint": "<thumbprint, uppercase, no spaces>",
       "digestAlgorithm": "sha256",
       "timestampUrl": "http://timestamp.digicert.com"
     }
   }
   ```

   A timestamp URL is required. Without it, every installer stops validating the
   moment the certificate expires, including copies users already downloaded.

4. Run the workflow manually with `sign: true` and confirm the
   **Verify Authenticode signature** step passes.

### EV certificates and HSMs

An EV certificate lives on hardware and cannot be exported, so the `.pfx` flow
above does not apply. The replacement is a cloud signing service — Azure Trusted
Signing, DigiCert KeyLocker, SSL.com eSigner — driven through Tauri's
`bundle.windows.signCommand`, which hands the artifact path to an external
command instead of using the certificate store. That swaps the two secrets for
service credentials and replaces the import step; the trust boundary, the
verification step, and the draft-release behaviour are unchanged.

### Rotation

- **Scheduled:** certificates are typically valid 1–3 years. Rotate at least 30
  days before expiry. Update both secrets, update `certificateThumbprint`, and
  run a manual signed build to confirm before the old certificate lapses.
- **Compromise:** revoke with the CA first, then rotate the secrets, then
  re-issue. Timestamped signatures made before the revocation date stay valid,
  which is the reason the timestamp URL is mandatory rather than optional.
- Rotation touches a tracked file (`tauri.conf.json`), so thumbprint changes go
  through review like any other change.

---

## Failure handling

| Failure | Behaviour | Rationale |
|---|---|---|
| Secrets missing | Preflight fails before any build work | An unsigned artifact must never be attached to a release |
| Thumbprint absent or wrong | `signtool verify` fails | Tauri emits an unsigned bundle rather than erroring, so verification is the only real detector |
| Certificate expired | `signtool verify` fails | Same detector, before publication |
| Timestamp server unreachable | Build fails | Signing without a timestamp produces an installer that expires with the certificate |
| Rust/Tauri build breaks | `unsigned-build` fails on the pull request | This is the coverage gap the issue is about |

Nothing in the signed path is best-effort. Every step that could silently
degrade the artifact is checked.

---

## Version and release behaviour

`scripts/bump_version.py --check` already runs in `ci.yml` and keeps
`backend/pyproject.toml`, `frontend/package.json`,
`frontend/src-tauri/Cargo.toml`, `Cargo.lock`, and `tauri.conf.json` on one
version. The workflow therefore reads the version from `frontend/package.json`
rather than accepting it as an input — a mismatch is not representable.

- Tag: `v<version>` — the same tag `publish.yml` uses for images, so a release
  has one tag covering both.
- The release is created as a **draft** and never published automatically.
- Re-running uploads with `--clobber`, so a re-signed artifact replaces the old
  one instead of appending a duplicate.
- `SHA256SUMS.txt` is generated in-job and attached, giving users a way to
  verify a download independently of the signature.

Publication stays manual: a maintainer opens the draft, checks the artifacts and
checksums, and presses publish.

---

## Extension points (not verified)

Described so the Windows design does not have to be redone later. Neither has
been run.

### macOS

Needs, beyond a `macos-latest` runner:

- A Developer ID Application certificate imported into a temporary keychain
  (not the login keychain — CI must not leave credentials behind).
- Notarization via `notarytool` with an App Store Connect API key, then
  `xcrun stapler staple` so the app validates offline.
- `APPLE_CERTIFICATE`, `APPLE_CERTIFICATE_PASSWORD`, `APPLE_SIGNING_IDENTITY`,
  `APPLE_API_KEY`, `APPLE_API_ISSUER` on the same environment.
- Universal binaries need both `aarch64-apple-darwin` and `x86_64-apple-darwin`
  targets installed.

Notarization is a network round-trip to Apple that can take minutes and can fail
for reasons unrelated to the build, so it needs its own retry and timeout
handling. Do not assume the Windows job's shape transfers.

### Linux

`.deb` and `.AppImage` come out of the same `tauri build`. Signing conventions
differ from Authenticode: repository signing uses a GPG key over package
metadata, and AppImage has its own embedded-signature scheme. Neither maps onto
`signtool verify`, so the verification step would need replacing rather than
parameterising.

Linux also has the `glib` advisory tracked in #383, which is inherited from
Tauri's gtk-rs 0.18 pin and is not fixable from this repository.

---

## Known blocker: the static export does not build

`unsigned-build` failed on its first run, and the cause is older than this
pipeline: `pnpm build:static` aborts because `/albums/[id]`, `/image/[id]`, and
`/public/shared/[key]` are client components with no `generateStaticParams()`,
which `output: export` requires. No installer can be produced at all until that
is resolved.

Two things make it more than a one-line fix: a client component cannot export
`generateStaticParams`, so each route needs a thin server wrapper; and an empty
param list is still rejected, so every dynamic route has to pre-render at least
one page. That forces a decision about what those routes even mean in a static
bundle, where runtime ids cannot resolve.

Tracked in #465. `unsigned-build` carries `continue-on-error` until it lands, so
the known break does not gate unrelated desktop pull requests — remove that flag
as part of the fix.

## Open questions

- Should `unsigned-build` become a required status check? It is a Windows runner
  and a cold cache costs roughly 15–20 minutes, so it is currently advisory.
- Should the signed path move from manual dispatch to firing on `v*` tags once a
  certificate exists? That would align it with `publish.yml`, at the cost of
  making every tag push depend on signing infrastructure being healthy.
- Tauri's built-in updater needs its own signing key
  (`TAURI_SIGNING_PRIVATE_KEY`), separate from Authenticode. Out of scope until
  an update channel exists.
