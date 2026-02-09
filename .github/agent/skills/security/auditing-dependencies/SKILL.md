---
name: auditing-dependencies
description: Analyze third-party libraries and supply chain risks to ensure no compromised or vulnerable code enters the project.
---

# Auditing Dependencies

## Goal
Maintain a "clean room" environment where every external package is verified, pinned, and free of known vulnerabilities (CVEs) or malicious maintainer practices.

## When to Use
- When adding a new dependency.
- During weekly maintenance cycles.
- When a security alert is published for the tech stack.

## Instructions

### 1. Scan for Known Vulnerabilities
Use ecosystem-specific tools to check against CVE databases.
- **Node/JS**: `npm audit` or `pnpm audit`.
- **Python**: `pip-audit` or `safety`.
- **General**: GitHub Dependabot alerts (if available).

### 2. Verify Package Health (Supply Chain Hygiene)
Before installing a package, check:
- **Maintenance**: Last commit date < 6 months ago?
- **Popularity/Community**: Stars, downloads, and active issues.
- **Maintainer Reputation**: Is it a solo dev with no history, or a recognized organization?
- **Typosquatting**: Double-check the spelling (e.g., `react` vs `raect`).

### 3. Pin Versions
Never use loose version ranges in production.
- **Good**: `"react": "18.2.0"` (Exact version)
- **Bad**: `"react": "^18.2.0"` (Allows updates that might introduce bugs or malware)
- **Lockfiles**: Ensure `package-lock.json`, `pnpm-lock.yaml`, or `poetry.lock` is committed.

### 4. Minimize Dependency Tree
- Do we need a 5MB library for a function we can write in 10 lines?
- "Tree-shaking" only helps bundle size; it doesn't prevent install-time scripts from running.

## Constraints

### ✅ Do
- Use a Software Bill of Materials (SBOM) approach: know exactly what is running.
- Audit *dev* dependencies too; they run on developer machines and CI servers.
- Automate dependency scanning in the CI/CD pipeline.
- Remove unused dependencies immediately.


### ❌ Don&#x27;t
- DO NOT ignore "moderate" severity alerts if they are easy to exploit.
- DO NOT install packages from unverified registries.
- DO NOT blind-update all packages without testing.


## Output Format
- Update `package.json` / `requirements.txt` with pinned versions.
- `AUDIT_LOG.md` entry confirming the check.

## Dependencies
- `shared/environment-config/SKILL.md`
