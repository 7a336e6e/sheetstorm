---
name: conducting-security-audit
description: Perform a rigorous, full-spectrum security assessment of the codebase, infrastructure, and logic flows to identify and remediate vulnerabilities.
---

# Conducting Security Audit

## Goal
Identify, document, and prescribe fixes for security vulnerabilities across the entire stack before they can be exploited. This is not a "check-the-box" exercise; it is a "break-the-system" mission.

## When to Use
- Before any major release or deployment.
- After adding significant new features (e.g., payment processing, new auth flows).
- Periodically (e.g., every sprint) to catch regression.

## Instructions

### 1. Static Analysis (SAST)
Scan the codebase for known vulnerability patterns using automated tools first, then manual verification.
- **Secrets Detection**: Ensure no keys, tokens, or credentials are committed.
- **Injection Flaws**: Grep for raw SQL queries (`execute(`), `eval()`, `innerHTML`, or `dangerouslySetInnerHTML`.
- **Configuration**: Verify `DEBUG=False` in production configs and strict CORS policies.

### 2. Logic Flow Review
Manually trace critical paths (Authentication, Authorization, Payments).
- **IDOR (Insecure Direct Object Reference)**: Can User A access `/users/B/orders` by changing the ID?
- **Business Logic Errors**: Can a user skip the "Payment" step and go straight to "Shipping"?
- **Race Conditions**: What happens if two requests hit the transfer endpoint simultaneously?

### 3. Dynamic Analysis (DAST) Simulation
Mentally or programmatically simulate attacks.
- **XSS**: Input `<script>alert(1)</script>` in every field.
- **CSRF**: Verify anti-CSRF tokens on all state-changing forms.
- **Auth Bypass**: Try accessing admin routes as a standard user.

### 4. Reporting
Create a `SECURITY_AUDIT.md` report.
- **Severity**: Critical (Immediate fix), High (Fix before release), Medium (Fix in backlog), Low (Note).
- **Proof of Concept**: specific steps to reproduce the exploit.
- **Remediation**: The exact code change required.

## Constraints

### ✅ Do
- Treat every user input as malicious until proven otherwise (Zero Trust).
- Verify that authorization checks happen *on the server*, never just the client.
- Check that all sensitive data (PII, passwords) is encrypted at rest and in transit.
- Validate that error messages do not leak stack traces or internal system details.
- Adhere to OWASP Top 10 2025 standards for Web Applications.


### ❌ Don&#x27;t
- DO NOT rely on "security by obscurity" (hiding a route doesn't secure it).
- DO NOT assume a library is secure just because it's popular; check its CVE history.
- DO NOT skip the audit because "we didn't change much." Small changes can break big security.
- DO NOT manually roll your own crypto. Use standard libraries (e.g., bcrypt, Argon2).


## Output Format
- `SECURITY_AUDIT.md`: A structured report of findings.
- **Blocker**: If Critical/High issues are found, block the release in `tasks.md`.

## Dependencies
- `../auditing-dependencies/SKILL.md`
- `../../backend/handling-errors/SKILL.md`
