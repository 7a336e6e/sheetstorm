# Security Policy

## Reporting a vulnerability

Please do **not** open a public issue for security problems.

Report vulnerabilities privately through GitHub's
[private vulnerability reporting](https://github.com/7a336e6e/sheetstorm/security/advisories/new)
("Report a vulnerability" under the repository's **Security** tab). Include:

- the affected component (backend, frontend, MCP server/bridge, proxy, Docker setup) and version or commit
- steps to reproduce or a proof of concept
- the impact you expect (e.g. cross-tenant data access, auth bypass, RCE)

We aim to acknowledge reports within 5 business days and to agree on a
disclosure timeline with you. Please give us a reasonable window to ship a fix
before publishing details.

## Supported versions

Only the latest `main` branch receives security fixes.

## Supply chain

Dependency and build hardening (lockfile-only installs, disabled install
scripts, release-age cooldown, hash-locked Python, digest-pinned images) and
the playbook for a compromised dependency are documented in
[assets/docs/supply-chain.md](assets/docs/supply-chain.md).

If you find a malicious or compromised package in SheetStorm's dependency
tree, report it the same way, and also to the registry (npm:
<https://www.npmjs.com/support>, PyPI: <https://pypi.org/security/>).
