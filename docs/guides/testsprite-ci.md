# TestSprite PR Testing

Find uses a GitHub Actions workflow to run TestSprite checks on pull requests.
The workflow is defined in `.github/workflows/testsprite.yml`.

## Required secret

Add this repository secret in GitHub:

```text
TESTSPRITE_API_KEY
```

Use a TestSprite API key for the connected Find project. Do not commit the key
to the repository.

## How it runs

- The workflow triggers on pull requests to `main`.
- Draft pull requests are skipped.
- Every non-draft PR is tested when the TestSprite secret is available.
- App PRs start `docker-compose.light.yml` in GitHub Actions.
- The light stack runs in mock ML mode, so it avoids GPU/model downloads.
- TestSprite is pointed at `http://127.0.0.1:3000`.

## Fork PR safety

Most GSSoC PRs come from forks. GitHub does not expose repository secrets to
normal `pull_request` workflows from untrusted forks, so TestSprite will skip
when `TESTSPRITE_API_KEY` is unavailable.

Do not move this workflow to `pull_request_target` just to expose secrets. That
would run contributor code with repository secrets and is unsafe.

For a fork PR that needs TestSprite verification, a maintainer can either:

- push the branch into the main repository and let the workflow run, or
- run the workflow manually with `workflow_dispatch` after reviewing the code.

## Manual run

Use **Actions → TestSprite PR Tests → Run workflow**.

Optional inputs:

- `base_url`: use this when testing an already-running preview deployment.
- `blocking`: set to `false` for exploratory runs that should not fail the job.

## Updating tests

Keep committed TestSprite tests in `testsprite_tests/`.

`testsprite_tests/PRD.md` is the canonical project brief for TestSprite. The
GitHub App and AI test generation flow may ask for a PRD before it can detect or
generate tests, so keep this file committed and updated when core product flows
change.

Best practice:

- keep the default PR suite stable and useful for every PR type
- cover API health plus critical upload, gallery, search, and clustering surfaces
- avoid brittle visual assertions in the default PR suite
- add focused tests when fixing regressions
