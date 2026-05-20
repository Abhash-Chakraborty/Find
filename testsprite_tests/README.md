# TestSprite Tests

This folder stores the committed TestSprite smoke-test plan used by the
`TestSprite PR Tests` GitHub Actions workflow.

The workflow runs against the light Docker Compose stack in mock ML mode on
every non-draft PR when the TestSprite API key is available. This gives every
PR, including docs/research PRs, a consistent smoke check without requiring GPU
model downloads.

Keep this suite stable and high-signal. Broader exploratory tests should be run
manually from the TestSprite dashboard or through `workflow_dispatch`.
