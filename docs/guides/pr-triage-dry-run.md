# PR triage automation dry-run checklist

This repository uses `.github/workflows/pr-triage.yml` to enforce baseline PR ownership checks.

## Trigger points

The workflow runs on `pull_request_target` for:

- `opened`
- `reopened`
- `synchronize`

It intentionally does **not** run on `edited` to reduce unnecessary runs.

## What it enforces

1. Adds `do-not-merge` to every triggered PR event.
2. Detects linked issues using closing keywords in PR body (`Fixes #123`, `Closes #123`, `Resolves #123`).
3. If no linked issue is found:
   - Adds `needs linked issue`.
   - Does not assign the PR.
4. If linked issue(s) exist:
   - Removes `needs linked issue` if present.
   - Assigns the PR to the PR author **only if** the author is assigned on at least one linked issue.
5. If the PR author is `dependabot[bot]`:
   - Adds `dependencies`.
   - Removes `needs linked issue` if present.
   - Does not assign the PR.
6. Ignores missing or invalid issue references instead of failing the workflow.
7. Checks only the first 10 unique linked issue references to keep API usage bounded.
8. Never closes PRs.
9. Never removes `do-not-merge` automatically.

## Manual verification matrix

### Case A: No linked issue in PR body

Expected:

- `do-not-merge` is present.
- `needs linked issue` is present.
- PR remains open.
- PR assignees are unchanged.

### Case B: Linked issue exists and PR author is assigned on that issue

Expected:

- `do-not-merge` is present.
- `needs linked issue` is absent.
- PR remains open.
- PR author is assigned to the PR.

### Case C: Linked issue exists but PR author is **not** assigned on that issue

Expected:

- `do-not-merge` is present.
- `needs linked issue` is absent.
- PR remains open.
- PR is **not** auto-assigned to PR author.

### Case D: Dependabot dependency PR

Expected:

- `do-not-merge` is present.
- `dependencies` is present.
- `needs linked issue` is absent.
- PR remains open.
- PR assignees are unchanged.

### Case E: PR body references a missing issue

Expected:

- Workflow does not fail just because one referenced issue is missing.
- Valid linked issues are still checked.
- If no valid linked issue assigns the PR author, PR assignees are unchanged.

## Permissions

The workflow is scoped to minimal required permissions:

- `issues: write`
- `pull-requests: write`

No source checkout is used, and no build/test jobs run in this workflow.
