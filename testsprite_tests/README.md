# TestSprite Tests

This folder stores the committed TestSprite smoke-test plan used by the
`TestSprite PR Tests` GitHub Actions workflow.

`PRD.md` is the product brief used by TestSprite's AI test generation and
GitHub App checks. Keep it broad and stable so PR-agnostic tests work for docs,
frontend, backend, and CI changes.

The workflow runs against the light Docker Compose stack in mock ML mode on
every non-draft PR when the TestSprite API key is available. This gives every
PR, including docs/research PRs, a consistent smoke check without requiring GPU
model downloads.

Keep this suite stable and high-signal. Broader exploratory tests should be run
manually from the TestSprite dashboard or through `workflow_dispatch`.
