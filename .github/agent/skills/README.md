# AI Agent Skills Boilerplate

A structured collection of skill files that guide AI coding agents through software engineering tasks. Designed for use with Claude Code, Gemini CLI, or any agent that follows the Agent Skills specification.

## What This Is

This repository contains a collection of markdown skill files organized across **11 agent roles**. Each skill file is a self-contained instruction set that tells an AI agent how to perform a specific software engineering task — from scaffolding a Flask app to designing a color system.

## Agent Roles

| Agent | Directory | Skills | Focus |
|-------|-----------|--------|-------|
| Agent Manager | `agent-manager/` | 3 | Task delegation, orchestration, quality review |
| Planner | `planner/` | 2 | Brainstorming, roadmapping, strategy |
| Product Manager | `product/` | 1 | User stories, acceptance criteria |
| Architect | `architect/` | 3 | Requirements analysis, system design, tech specs |
| Designer | `designer/` | 5 | Brand identity, design systems, layouts, a11y |
| Frontend Engineer | `frontend/` | 6 | React + TypeScript + Vite |
| Backend Engineer | `backend/` | 6 | Flask + RESTful APIs |
| Database Engineer | `database/` | 5 | PostgreSQL + SQLAlchemy + Alembic |
| Auth Engineer | `auth/` | 4 | Local auth, OAuth, JWT, security |
| Security Engineer | `security/` | 3 | Audits, dependency vetting, agent hardening |
| DevOps Engineer | `devops/` | 1 | CI/CD, infrastructure, deployment |

All agents share 7 cross-cutting skills in `shared/`.

## How It Works

1. **Start**: The Agent Manager reads `AGENTS.md` to understand the team
2. **Plan**: The Architect analyzes requirements and produces a technical spec
3. **Execute**: Domain agents execute tasks using their SKILL.md files
4. **Track**: All tasks live in `tasks.md` at the project root
5. **Review**: The Agent Manager reviews output through quality gates

## File Structure

- `AGENTS.md` — Master orchestration document (start here)
- `tasks.md` — Global task tracker (Jira-style, single source of truth)
- `templates/` — Canonical templates for tasks and skills
- `shared/` — Cross-cutting skills used by all agents
- `{agent}/` — Agent-specific skills, each in `{skill-name}/SKILL.md`
- `references/` — Supporting detail docs within skill directories

## Skill File Format

Every `SKILL.md` follows a consistent structure:

- **Frontmatter** — Name, description
- **Goal** — One-sentence success definition
- **When to Use** — Trigger conditions
- **Instructions** — Step-by-step process with code examples
- **Constraints** — `### ✅ Do` and `### ❌ Don&#x27;t` tags for best/worst practices
- **Output Format** — What the agent should produce
- **Dependencies** — Links to prerequisite skills

## Customization

To adapt this for your stack:

1. Fork/copy this directory
2. Modify agent roles and skills to match your team structure
3. Update technology references (e.g., swap Flask for FastAPI, React for Svelte)
4. Keep the file format consistent — agents rely on the section structure

## Design Principles

- **Gerund naming** for skill directories (`scaffolding-flask/`, not `scaffold-flask/`)
- **Max 150 lines** per SKILL.md — depth goes in `references/` subdirectories
- **Single tasks.md** — prevents conflicting task numbers across agents
- **Max 1-hop references** — every skill links directly to what it needs
- **Machine-parseable constraints** — `### ✅ Do`/`### ❌ Don&#x27;t` XML tags for structured rules
