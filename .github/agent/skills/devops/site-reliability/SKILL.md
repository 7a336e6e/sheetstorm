---
name: Site Reliability Engineering
description: Define Service Level Objectives (SLOs), manage Error Budgets, and conduct Incident Reviews to balance reliability with velocity.
---

# Site Reliability Engineering (SRE)

## Goal
Treat operations as a software problem. Quantify reliability so we know exactly when to freeze deployments (reliability at risk) and when to push fast (error budget available).

## When to Use
- When defining "Is it stable enough?" criteria.
- After a production outage (Post-Mortem).
- When planning on-call rotations.

## Instructions

### 1. Define SLIs (Service Level Indicators)
What is "good"?
- **Availability**: Successful requests / Total requests.
- **Latency**: Requests faster than 200ms / Total requests.

### 2. Set SLOs (Service Level Objectives)
What is the target? (100% is impossible).
- **Target**: "99.9% of requests in 30 days are successful."
- **Window**: Rolling 28 or 30 days.

### 3. Manage Error Budgets
`(100% - SLO) = Error Budget`.
- If you have 0.1% budget, you can fail 43 minutes a month.
- **Rule**: If budget is exhausted -> **Code Freeze**. Only reliability fixes allowed.

### 4. Incident Management
When things break:
1. **Detect**: Alert fires.
2. **Respond**: Acknowledge, triage, stabilize (mitigate impact).
3. **Analyze**: Root cause analysis (5 Whys).
4. **Learn**: Create action items to prevent recurrence.

## Constraints

### ✅ Do
- **DO**: Blameless Post-Mortems. Focus on process failure, not human error.
- **DO**: Automate runbooks. If you run a command twice, script it.
- **DO**: Measure what matters to the *user* (Client-side latency), not just the server.

### ❌ Don't
- **DON'T**: Alert on things you can't fix immediately.
- **DON'T**: Page the whole team. Page the on-call engineer.
- **DON'T**: Optimize reliability past the SLO (diminishing returns).

## Output Format
- `SLOs.md`: Definitions of SLIs and targets.
- `post-mortems/YYYY-MM-DD-incident.md`: Incident review records.

## Dependencies
- `devops/implementing-observability/SKILL.md`
