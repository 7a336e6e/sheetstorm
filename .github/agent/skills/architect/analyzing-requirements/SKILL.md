---
name: Analyzing Requirements
description: Translate natural-language requirements into structured, prioritized specifications with clear acceptance criteria.
---

# Analyzing Requirements

## Goal

Parse user stories, feature requests, vague descriptions, or stakeholder conversations into a structured requirements document that can drive architecture and implementation decisions.

## When to Use

- A user describes a feature or product idea in natural language
- You receive user stories that need formalization
- Requirements exist but are unstructured, incomplete, or ambiguous
- You need to prepare input for the `designing-architecture` skill

## Instructions

### 1. Gather Raw Input

Collect all available information: user stories, feature requests, stakeholder notes, existing documentation, or conversational descriptions. If the input is thin, ask clarifying questions before proceeding.

### 2. Identify User Roles

Extract every distinct user role or actor mentioned or implied. For each role, define their goals, permissions, and relationship to other roles.

### 3. Extract Functional Requirements

Break the input into discrete functional requirements. Each requirement should describe a single capability the system must provide.

For each requirement, assign:
- **ID**: A unique identifier (e.g., `FR-001`)
- **Description**: A clear, testable statement of what the system does
- **Priority**: Using MoSCoW classification (Must-have, Should-have, Could-have, Won't-have)
- **Acceptance Criteria**: Concrete conditions that prove the requirement is met

**Example**: The input _"users should be able to sign up and manage their profile"_ becomes:

| ID     | Description                                         | Priority  | Acceptance Criteria                                                        |
|--------|-----------------------------------------------------|-----------|----------------------------------------------------------------------------|
| FR-001 | Users can register with email and password           | Must-have | User submits form, receives confirmation email, account is created in DB   |
| FR-002 | Users can log in with registered credentials         | Must-have | User enters valid credentials, receives session token, is redirected home  |
| FR-003 | Users can view their profile page                    | Must-have | Logged-in user sees name, email, and avatar on /profile                    |
| FR-004 | Users can edit their display name and avatar          | Should-have | User updates fields, clicks save, changes persist on refresh             |
| FR-005 | Users can change their password                      | Should-have | User provides current + new password, new password applies on next login  |
| FR-006 | Users can delete their account                       | Could-have | User confirms deletion, account and data are removed within 30 days       |

### 4. Extract Non-Functional Requirements

Identify requirements that describe system qualities rather than features:
- **Performance**: Response times, throughput, concurrent users
- **Security**: Authentication, authorization, data encryption, compliance
- **Scalability**: Growth expectations, horizontal vs vertical scaling needs
- **Accessibility**: WCAG level, screen reader support, keyboard navigation
- **Reliability**: Uptime targets, disaster recovery, data backup

### 5. Map Data Entities and Relationships

Identify the core data entities, their fields, and how they relate to each other. This feeds directly into data model design.

### 6. Identify Workflows

Trace end-to-end user workflows that span multiple requirements. Document the happy path and the most important error paths.

### 7. Log Open Questions

Any ambiguity that cannot be resolved from the available input should be logged as an open question, not silently assumed.

### 8. Produce the Requirements Document

Compile everything into a structured document following the template in `references/requirement-template.md`.

## Constraints

### ✅ Do
- Ask clarifying questions when input is ambiguous or incomplete
- Identify edge cases and error scenarios for each requirement
- Define measurable acceptance criteria for every functional requirement
- Prioritize using MoSCoW and justify the classification
- Separate functional from non-functional requirements
- Cross-reference requirements that depend on each other
- Log every assumption explicitly


### ❌ Don&#x27;t
- Assume missing details; flag them as open questions instead
- Gold-plate requirements by adding capabilities the user did not request
- Skip non-functional requirements even if the user only describes features
- Write vague acceptance criteria like "works correctly" or "is fast"
- Combine multiple independent capabilities into a single requirement
- Ignore security and accessibility unless explicitly told they are out of scope


## Output Format

A Markdown document following the structure defined in `references/requirement-template.md`. The document should be self-contained and readable by both technical and non-technical stakeholders.

Key sections:
1. Project Overview
2. User Roles
3. Functional Requirements (grouped by domain)
4. Non-Functional Requirements
5. Data Entities
6. API Surface (preliminary)
7. Open Questions

## Dependencies

- `../../shared/task-tracking/SKILL.md` -- for tracking progress on requirement gathering
- `references/requirement-template.md` -- structural template for the output document
