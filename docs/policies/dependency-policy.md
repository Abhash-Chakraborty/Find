# Dependency Management and Vulnerability Policy

Find uses separate dependency ecosystems for the frontend and backend. This
policy keeps routine updates reproducible, gives newly published packages time
to be reviewed by the wider ecosystem, and leaves room for urgent security
patches when they are needed.

## Frontend: pnpm

- Keep `pnpm-lock.yaml` committed so local installs and CI resolve the same
  dependency graph.
- Use pnpm's `minimumReleaseAge` setting to delay routine adoption of newly
  published package versions for 7 days.
- Keep emergency exceptions explicit with `minimumReleaseAgeExclude` only when a
  maintainer decides that a specific security or compatibility fix should be
  adopted immediately.
- Treat `pnpm audit --audit-level=high` as a report for maintainer review. It is
  currently non-blocking so unrelated PRs are not stopped by pre-existing
  advisories.

## Backend: uv

- Keep `uv.lock` committed and use `uv sync --locked` in CI so the lockfile
  remains the source of truth.
- Use normal Python review practices instead of copying npm-specific cooldown
  behavior into the backend ecosystem.
- Run `pip-audit` in CI against the locked backend environment as a report for
  maintainer review.
- Test important dependency changes in both the full GPU stack and the light
  mock-mode stack when they can affect ML processing, embeddings, or packaging.

## Review cadence

- Review routine dependency updates in batches instead of merging them
  immediately after publication.
- Review high or critical advisories as soon as they are reported.
- For emergency fixes, document why the normal delay was bypassed and keep the
  exception as narrow as possible.

## Pull request expectations

- Keep dependency policy changes separate from bulk dependency upgrades unless a
  maintainer explicitly asks for both in the same PR.
- Include updated lockfiles when dependency manifests change.
- Explain whether an update is routine, security-driven, or an emergency
  exception to the normal delay.
- Keep CI comments and documentation aligned with the actual workflow behavior.

## Current implementation

- `frontend/pnpm-workspace.yaml` sets `minimumReleaseAge: 10080`, which is 7
  days in minutes.
- `.github/workflows/ci.yml` uses a pnpm version that supports
  `minimumReleaseAge`.
- Frontend and backend vulnerability audits are currently report-only. They are
  intended to inform maintainer review, not automatically block every PR.
