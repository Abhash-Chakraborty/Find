# Security Policy

## Supported Versions

Find is under active development. Security fixes are prepared privately,
validated through `canary`, and released from the current `main` branch.

## Reporting a Vulnerability

Please report security vulnerabilities privately using GitHub's **Report a
vulnerability** option for this repository. Do not open public issues for
security reports.

Helpful reports include:

- the affected feature or file
- the security impact
- clear reproduction steps
- a suggested fix, if you already have one

Please allow maintainers time to review and verify reports before public
disclosure so fixes can be prepared responsibly.

Maintainers should use a patch version for a backward-compatible security fix.
After the private fix is reviewed and promoted from `canary` to `main`, the
release workflow may be manually dispatched with the emergency option to skip
the normal three-hour quiet period. The branch-policy bypass is reserved for a
last-resort production incident and does not replace review or disclosure.
