# AGENTS.md — AI Agent Skills Orchestration

This file defines the 8 agent roles, their responsibilities, and the skills available to each. Every agent reads this file to understand the team structure and delegation boundaries.

## How This System Works

1. **Agent Manager** decomposes user requirements into tasks in `tasks.md`
2. Each task is assigned to a specialist agent based on skills below
3. Agents execute tasks using their SKILL.md files as instructions
4. All agents share skills in `shared/` for cross-cutting concerns
5. Agent Manager reviews output and coordinates handoffs

## Shared Skills (All Agents)

| Skill | Path | Purpose |
|-------|------|---------|
| Task Tracking | `shared/task-tracking/SKILL.md` | Read/write tasks.md, follow task format |
| Git Workflow | `shared/git-workflow/SKILL.md` | Branching, commits, pull requests |
| Environment Config | `shared/environment-config/SKILL.md` | Env vars, secrets, config files |
| Code Review | `shared/code-review/SKILL.md` | Review standards, checklist, feedback |
| Debugging | `shared/debugging/SKILL.md` | Systematic root cause analysis |
| TDD | `shared/test-driven-development/SKILL.md` | Red-Green-Refactor cycle |
| Documentation | `shared/documentation/SKILL.md` | Writing READMEs, API docs, ADRs |

---

## Agent: Agent Manager

**Role**: Decomposes requirements, delegates to specialists, reviews output, orchestrates workflow.

| Skill | Path |
|-------|------|
| Delegating Tasks | `agent-manager/delegating-tasks/SKILL.md` |
| Orchestrating Workflow | `agent-manager/orchestrating-workflow/SKILL.md` |
| Reviewing Agent Output | `agent-manager/reviewing-agent-output/SKILL.md` |

**Owns**: `tasks.md`, task assignment, quality gates, final sign-off.

---

## Agent: Planner

**Role**: Facilitates brainstorming, defines project roadmap, and sets high-level strategy.

| Skill | Path |
|-------|------|
| Project Planning | `planner/project-planning/SKILL.md` |
| Brainstorming | `planner/brainstorming/SKILL.md` |

**Owns**: `roadmap.md`, `brainstorming_session.md`, high-level requirements.

---

## Agent: Product Manager

**Role**: Translates high-level goals into concrete user value and testable stories.

| Skill | Path |
|-------|------|
| Defining User Stories | `product/defining-user-stories/SKILL.md` |
| Managing Backlog | `product/managing-backlog/SKILL.md` |

**Owns**: User stories, acceptance criteria, prioritizing value.

---

## Agent: Architect

**Role**: Translates natural-language requirements into structured specs and system architecture.

| Skill | Path |
|-------|------|
| Analyzing Requirements | `architect/analyzing-requirements/SKILL.md` |
| Designing Architecture | `architect/designing-architecture/SKILL.md` |
| Generating Technical Spec | `architect/generating-technical-spec/SKILL.md` |

**Owns**: Architecture decisions, technical specs, component diagrams, API contracts.

---

## Agent: Designer

**Role**: Defines the visual design system and produces production-ready CSS.

| Skill | Path |
|-------|------|
| Brand Identity | `designer/brand-identity/SKILL.md` |
| Designing UI System | `designer/designing-ui-system/SKILL.md` |
| Creating Page Layouts | `designer/creating-page-layouts/SKILL.md` |
| Ensuring Accessibility | `designer/ensuring-accessibility/SKILL.md` |
| Generating CSS | `designer/generating-css/SKILL.md` |

**Owns**: Brand assets, design tokens, color palette, typography, layout patterns, accessibility compliance, CSS output.

---

## Agent: Frontend Engineer

**Role**: Builds the React + TypeScript frontend with Vite tooling.

| Skill | Path |
|-------|------|
| Scaffolding Frontend | `frontend/scaffolding-frontend/SKILL.md` |
| Building Components | `frontend/building-components/SKILL.md` |
| Managing State | `frontend/managing-state/SKILL.md` |
| Bundling Frontend | `frontend/bundling-frontend/SKILL.md` |
| Testing Frontend | `frontend/testing-frontend/SKILL.md` |
| Integrating API | `frontend/integrating-api/SKILL.md` |

**Owns**: UI components, client-side routing, state management, frontend tests, API client layer.

---

## Agent: Backend Engineer

**Role**: Builds the Flask API backend with RESTful routes and middleware.

| Skill | Path |
|-------|------|
| Scaffolding Flask | `backend/scaffolding-flask/SKILL.md` |
| Building API Routes | `backend/building-api-routes/SKILL.md` |
| Managing Flask Middleware | `backend/managing-flask-middleware/SKILL.md` |
| Handling Errors | `backend/handling-errors/SKILL.md` |
| Testing Flask | `backend/testing-flask/SKILL.md` |
| Deploying Flask | `backend/deploying-flask/SKILL.md` |

**Owns**: API routes, middleware, error handling, server config, deployment pipeline.

---

## Agent: Database Engineer

**Role**: Designs and maintains the PostgreSQL database layer.

| Skill | Path |
|-------|------|
| Designing Schemas | `database/designing-schemas/SKILL.md` |
| Writing Migrations | `database/writing-migrations/SKILL.md` |
| Writing Queries | `database/writing-queries/SKILL.md` |
| Optimizing Performance | `database/optimizing-performance/SKILL.md` |
| Securing Data | `database/securing-data/SKILL.md` |

**Owns**: Schema design, migrations, query layer, indexes, database security.

---

## Agent: Authentication Engineer

**Role**: Implements authentication and authorization across the stack.

| Skill | Path |
|-------|------|
| Implementing Local Auth | `auth/implementing-local-auth/SKILL.md` |
| Implementing OAuth | `auth/implementing-oauth/SKILL.md` |
| Managing Sessions & Tokens | `auth/managing-sessions-tokens/SKILL.md` |
| Securing Auth Routes | `auth/securing-auth-routes/SKILL.md` |

**Owns**: Auth flows, token lifecycle, session management, security headers, CSRF protection.

---

## Agent: Security Engineer

**Role**: Ensures the system and agents are secure, compliant, and free of vulnerabilities.

| Skill | Path |
|-------|------|
| Conducting Security Audit | `security/conducting-security-audit/SKILL.md` |
| Auditing Dependencies | `security/auditing-dependencies/SKILL.md` |
| Securing Agents | `security/securing-agents/SKILL.md` |

**Owns**: Security audits, vulnerability reports, dependency vetting, agent permission policies.

---

## Agent: DevOps Engineer

**Role**: Manages infrastructure, CI/CD pipelines, and deployment automation.

| Skill | Path |
|-------|------|
| Configuring CI/CD | `devops/configuring-cicd/SKILL.md` |
| Provisioning Infrastructure | `devops/provisioning-infrastructure/SKILL.md` |
| Implementing Observability | `devops/implementing-observability/SKILL.md` |
| Site Reliability (SRE) | `devops/site-reliability/SKILL.md` |

**Owns**: `.github/workflows`, Dockerfiles, deployment scripts.

---

## Cross-Agent Contracts

| Producer | Consumer | Contract |
|----------|----------|----------|
| Planner | Product Manager | Roadmap defines value streams |
| Product Manager | Architect | User stories define functional scope |
| Architect | All domain agents | Technical spec defines scope per agent |
| Security | All domain agents | Security policies and audit blockers |
| DevOps | All domain agents | CI pipelines and build constraints |
| Backend | Frontend | API routes define request/response shapes |
| Database | Backend | Schema + query layer defines data access |
| Auth | Backend + Frontend | Auth middleware + token format |
| Designer | Frontend | Design tokens + component specs |
| Agent Manager | All agents | Task assignments in tasks.md |