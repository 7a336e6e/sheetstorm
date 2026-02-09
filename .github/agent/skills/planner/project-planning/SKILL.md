---
name: project-planning
description: Define project scope, milestones, MVP requirements, and roadmap to turn vague ideas into executable plans.
---

# Project Planning

## Goal
Transform a high-level goal or vague idea into a structured, actionable roadmap with clear milestones, defined MVP scope, and identified risks.

## When to Use
- At the start of a new project.
- When a project's scope is creeping or undefined.
- When needing to prioritize features for an MVP.

## Instructions

### 1. Define the North Star
Identify the core value proposition.
- **Problem**: What specific pain point are we solving?
- **Solution**: How do we solve it better than alternatives?
- **Audience**: Who exactly is this for?

### 2. Establish the MVP (Minimum Viable Product)
Ruthlessly cut features to the absolute minimum required to solve the core problem.
- **Must Have**: Non-negotiable features.
- **Should Have**: Important but can wait for v1.1.
- **Could Have**: Nice to have.
- **Won't Have**: Explicitly out of scope for now.

### 3. Phases and Milestones
Break the timeline into logical chunks.

- **Phase 1: Foundation** (Scaffolding, Auth, DB schema)
- **Phase 2: Core Loop** (The main feature user interacts with)
- **Phase 3: Polish** (UI cleanup, error handling, onboarding)
- **Phase 4: Launch** (Deployment, smoke testing)

### 4. Risk Assessment
Identify what could go wrong.
- **Technical Risks**: "We don't know how to use this API."
- **Product Risks**: "Users might not understand the workflow."
- **Mitigation**: "Build a prototype first" or "Add tooltips."

## Constraints

### ✅ Do
- Prioritize "Core Loop" features over administrative features (like "Edit Profile") in the MVP.
- Define "Done" criteria for each milestone.
- Focus on user outcomes, not just technical tasks.
- keep the MVP timeline under 4 weeks if possible.


### ❌ Don&#x27;t
- DO NOT plan more than one phase ahead in detail. Things change.
- DO NOT allow "scope creep" without removing something else of equal size.
- DO NOT skip the "Why". Every feature must map back to the North Star.


## Output Format
- `roadmap.md`: A high-level timeline of phases.
- Updates to `tasks.md` (high-level epics).

## Dependencies
- `../../architect/analyzing-requirements/SKILL.md`
