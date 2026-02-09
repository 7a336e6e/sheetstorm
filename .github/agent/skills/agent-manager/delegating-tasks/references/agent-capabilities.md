---
name: Agent Capabilities Reference
description: Master map of all agents, their skills, technologies, and assignment guidance.
---

# Agent Capabilities Reference

This is the canonical reference for all agents in the system. Use it when deciding which agent should own a task.

---

## Agent Manager

**Role:** Coordinates the team — decomposes requirements, delegates tasks, orchestrates workflows, and reviews output.

| Skill | Path | Description |
|-------|------|-------------|
| Delegating Tasks | `agent-manager/delegating-tasks/SKILL.md` | Decompose requirements and assign tasks to agents |
| Orchestrating Workflow | `agent-manager/orchestrating-workflow/SKILL.md` | Manage execution order, parallelism, and blocked tasks |
| Reviewing Agent Output | `agent-manager/reviewing-agent-output/SKILL.md` | Quality gates, acceptance criteria verification, integration checks |

**Key strengths:** Project decomposition, cross-agent coordination, dependency management, quality assurance.
**Technologies:** Markdown task tracking, workflow patterns, review checklists.

---

## Planner

**Role:** Facilitates brainstorming, defines project roadmap, and sets high-level strategy.

| Skill | Path | Description |
|-------|------|-------------|
| Project Planning | `planner/project-planning/SKILL.md` | Create project roadmaps and milestones |
| Brainstorming | `planner/brainstorming/SKILL.md` | Facilitate ideation sessions and capture ideas |

**Key strengths:** Strategic thinking, stakeholder alignment, timeline estimation, scope definition.
**Technologies:** Markdown roadmaps, Gantt charts, milestone tracking.
**Assign when:** Starting a new project, defining scope, or planning sprints.

---

## Product Manager

**Role:** Translates high-level goals into concrete user value and testable stories.

| Skill | Path | Description |
|-------|------|-------------|
| Defining User Stories | `product/defining-user-stories/SKILL.md` | Write user stories with acceptance criteria |
| Managing Backlog | `product/managing-backlog/SKILL.md` | Prioritize and groom the product backlog |

**Key strengths:** User empathy, value prioritization, acceptance criteria, stakeholder communication.
**Technologies:** User story format, backlog management, prioritization frameworks.
**Assign when:** Defining features, writing acceptance criteria, or prioritizing work.

---

## Architect

**Role:** Designs system structure — analyzes requirements, creates architecture, and generates technical specs.

| Skill | Path | Description |
|-------|------|-------------|
| Analyzing Requirements | `architect/analyzing-requirements/SKILL.md` | Parse requirements into structured specs |
| Designing Architecture | `architect/designing-architecture/SKILL.md` | Define system components and boundaries |
| Generating Technical Spec | `architect/generating-technical-spec/SKILL.md` | Create implementation tasks from architecture |

**Key strengths:** Big-picture thinking, cross-cutting technical decisions, establishing contracts that other agents build against.
**Technologies:** System diagrams, OpenAPI/Swagger, ERD notation, ADRs (Architecture Decision Records).
**Assign when:** Work requires defining structure before implementation begins, or a technical decision affects multiple agents.

---

## Designer

**Role:** Defines the visual design system and produces production-ready CSS.

| Skill | Path | Description |
|-------|------|-------------|
| Brand Identity | `designer/brand-identity/SKILL.md` | Define brand values, personality, and visual language |
| Designing UI System | `designer/designing-ui-system/SKILL.md` | Create design tokens, color palette, typography |
| Creating Page Layouts | `designer/creating-page-layouts/SKILL.md` | Define page structure, grids, visual hierarchy |
| Ensuring Accessibility | `designer/ensuring-accessibility/SKILL.md` | WCAG 2.2 AA compliance and testing |
| Generating CSS | `designer/generating-css/SKILL.md` | Produce Tailwind config and CSS from design tokens |

**Key strengths:** Visual consistency, responsive design, accessibility compliance, design system thinking.
**Technologies:** Design tokens, Tailwind CSS, CSS custom properties, WCAG guidelines.
**Assign when:** Work involves visual appearance, layout decisions, or design system updates.

---

## Frontend Engineer

**Role:** Builds the React + TypeScript frontend with Vite tooling.

| Skill | Path | Description |
|-------|------|-------------|
| Scaffolding Frontend | `frontend/scaffolding-frontend/SKILL.md` | Vite + React + TypeScript project setup |
| Building Components | `frontend/building-components/SKILL.md` | Create reusable UI components |
| Managing State | `frontend/managing-state/SKILL.md` | Zustand, TanStack Query, React Context |
| Bundling Frontend | `frontend/bundling-frontend/SKILL.md` | Vite config and build optimization |
| Testing Frontend | `frontend/testing-frontend/SKILL.md` | Vitest, Testing Library, Playwright |
| Integrating API | `frontend/integrating-api/SKILL.md` | Typed API client and error handling |

**Key strengths:** Component architecture, responsive UI, client-side performance, accessibility.
**Technologies:** React, TypeScript, Vite, Tailwind CSS, Zustand, TanStack Query.
**Assign when:** Work involves anything the user sees or interacts with in the browser.

---

## Backend Engineer

**Role:** Builds the Flask API backend with RESTful routes and middleware.

| Skill | Path | Description |
|-------|------|-------------|
| Scaffolding Flask | `backend/scaffolding-flask/SKILL.md` | App factory pattern and blueprint setup |
| Building API Routes | `backend/building-api-routes/SKILL.md` | RESTful routes with validation |
| Managing Flask Middleware | `backend/managing-flask-middleware/SKILL.md` | CORS, rate limiting, security headers |
| Handling Errors | `backend/handling-errors/SKILL.md` | Centralized error handling |
| Testing Flask | `backend/testing-flask/SKILL.md` | pytest, fixtures, test client |
| Deploying Flask | `backend/deploying-flask/SKILL.md` | Gunicorn, Nginx, Docker |

**Key strengths:** API implementation, business rule enforcement, input validation, error handling.
**Technologies:** Flask, Python, Gunicorn, Docker, pytest.
**Assign when:** Work involves server-side logic, API implementation, or anything between the frontend and the database.

---

## Database Engineer

**Role:** Designs and maintains the PostgreSQL database layer.

| Skill | Path | Description |
|-------|------|-------------|
| Designing Schemas | `database/designing-schemas/SKILL.md` | Schema design and normalization |
| Writing Migrations | `database/writing-migrations/SKILL.md` | Alembic migration patterns |
| Writing Queries | `database/writing-queries/SKILL.md` | SQLAlchemy ORM and raw SQL |
| Optimizing Performance | `database/optimizing-performance/SKILL.md` | Indexes, EXPLAIN, query tuning |
| Securing Data | `database/securing-data/SKILL.md` | Encryption, RLS, backups |

**Key strengths:** Schema design implementation, query performance, data integrity constraints, migration safety.
**Technologies:** PostgreSQL, SQLAlchemy, Alembic, database indexing.
**Assign when:** Work involves database schema changes, complex queries, or data management.

---

## Authentication Engineer

**Role:** Implements authentication and authorization across the stack.

| Skill | Path | Description |
|-------|------|-------------|
| Implementing Local Auth | `auth/implementing-local-auth/SKILL.md` | Registration, login, bcrypt |
| Implementing OAuth | `auth/implementing-oauth/SKILL.md` | GitHub/Google OAuth via Authlib |
| Managing Sessions & Tokens | `auth/managing-sessions-tokens/SKILL.md` | JWT, refresh tokens, cookies |
| Securing Auth Routes | `auth/securing-auth-routes/SKILL.md` | CSRF, rate limiting, HTTPS |

**Key strengths:** Security-first thinking, token lifecycle management, permission modeling, vulnerability prevention.
**Technologies:** JWT, OAuth 2.0, bcrypt, Authlib, session management.
**Assign when:** Work involves user identity, access control, or anything security-sensitive.

---

## Security Engineer

**Role:** Ensures the system and agents are secure, compliant, and free of vulnerabilities.

| Skill | Path | Description |
|-------|------|-------------|
| Conducting Security Audit | `security/conducting-security-audit/SKILL.md` | OWASP-based security reviews |
| Auditing Dependencies | `security/auditing-dependencies/SKILL.md` | Dependency vulnerability scanning |
| Securing Agents | `security/securing-agents/SKILL.md` | Agent permission policies and sandboxing |

**Key strengths:** Threat modeling, vulnerability assessment, compliance, secure coding practices.
**Technologies:** OWASP guidelines, dependency scanners, security headers, penetration testing.
**Assign when:** Security review needed, dependencies must be vetted, or agent permissions need defining.

---

## DevOps Engineer

**Role:** Manages infrastructure, CI/CD pipelines, and deployment automation.

| Skill | Path | Description |
|-------|------|-------------|
| Configuring CI/CD | `devops/configuring-cicd/SKILL.md` | GitHub Actions, pipelines, automated testing |
| Provisioning Infrastructure | `devops/provisioning-infrastructure/SKILL.md` | Docker, cloud resources, IaC |
| Implementing Observability | `devops/implementing-observability/SKILL.md` | Logging, metrics, tracing |
| Site Reliability (SRE) | `devops/site-reliability/SKILL.md` | Uptime, incident response, SLOs |

**Key strengths:** Automation, infrastructure as code, monitoring, reliability engineering.
**Technologies:** GitHub Actions, Docker, Terraform, Prometheus, Grafana.
**Assign when:** Work involves CI/CD, deployment, infrastructure, or observability.

---

## Shared Skills (Available to All Agents)

These skills are not owned by a single agent. Any agent can use them as part of their work.

| Skill | Path | Description |
|-------|------|-------------|
| Task Tracking | `shared/task-tracking/SKILL.md` | Read and update task status in tasks.md |
| Git Workflow | `shared/git-workflow/SKILL.md` | Branching, commits, pull request conventions |
| Environment Config | `shared/environment-config/SKILL.md` | Env vars, secrets, config files |
| Code Review | `shared/code-review/SKILL.md` | Review conventions, feedback format, approval criteria |
| Debugging | `shared/debugging/SKILL.md` | Systematic root cause analysis |
| TDD | `shared/test-driven-development/SKILL.md` | Red-Green-Refactor cycle |
| Documentation | `shared/documentation/SKILL.md` | Writing READMEs, API docs, ADRs |

---

## Quick Assignment Guide

| If the task involves... | Assign to |
|------------------------|-----------|
| Project roadmap, milestones, strategy | Planner |
| User stories, acceptance criteria, backlog | Product Manager |
| System design, API contracts, tech specs | Architect |
| Brand identity, design tokens, visual polish | Designer |
| UI components, pages, client state | Frontend Engineer |
| API endpoints, business logic, middleware | Backend Engineer |
| Database schema, migrations, queries | Database Engineer |
| Login, permissions, tokens, security | Auth Engineer |
| Security audits, vulnerability scanning | Security Engineer |
| CI/CD, infrastructure, deployment | DevOps Engineer |
| Task breakdown, coordination, reviews | Agent Manager |
