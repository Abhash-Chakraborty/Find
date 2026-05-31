Apply these rules when reviewing changes under `.github/**` and automation scripts.

Workflow review priorities:
- Prefer manual or label-gated automation over noisy always-on review bots.
- For `pull_request_target`, do not execute untrusted PR code or expose secrets to forked changes.
- Keep PR automation explainable: if labels, assignments, or review triggers change, the workflow should leave a visible summary or comment.
- Flag automation that could accidentally review, approve, or merge `do-not-merge` pull requests.
- Prefer one sticky summary comment over repeated bot spam on every synchronize event.
