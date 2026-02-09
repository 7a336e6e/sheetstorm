---
name: securing-agents
description: Enforce safeguards specifically for AI Agents to prevent prompt injection, tool misuse, and excessive autonomy (OWASP Top 10 for Agents).
---

# Securing Agents

## Goal
Prevent AI Agents from being manipulated into performing harmful actions, leaking context, or executing malicious code. Secure the "Agentic Supply Chain."

## When to Use
- When defining a new agent's tools or permissions.
- When designing the prompt/system instruction for an agent.
- When integrating an agent with external APIs or databases.

## Instructions

### 1. Least Privilege (Agency Control)
Agents should only have the permissions strictly necessary for their specific task.
- **Tools**: If an agent reads files, don't give it `write_file` access unless required.
- **Scope**: Restrict file system access to specific directories (Sandboxing).
- **Approval**: Require human-in-the-loop (HITL) for high-impact actions (e.g., `delete_database`, `deploy_production`).

### 2. Prompt Injection Defense
Sanitize and segment inputs to prevent "Ignore previous instructions" attacks.
- **Delimiters**: Use XML tags (e.g., `<user_input>...</user_input>`) to clearly separate data from instructions.
- **System Prompt Hardening**: Explicitly instruct the agent to prioritize system instructions over user input.
- **Output Validation**: Check if the agent's output looks like it was hijacked (e.g., suddenly speaking a different language or dumping internal state).

### 3. Tool Input Validation (Zero Trust)
Never assume the agent generated safe arguments for a tool.
- **Validation**: Use Zod/Pydantic to strictly validate the *structure* and *content* of tool arguments.
- **Sanitization**: Prevent command injection (e.g., if a tool runs a shell command, escape all arguments).

### 4. Monitoring & Observability
- **Log Everything**: Inputs, outputs, tool calls, and reasoning steps.
- **Anomaly Detection**: Flag if an agent tries to access `/.env` or `/etc/passwd`.
- **Circuit Breakers**: If an agent fails or errors 3 times in a row, kill the process to prevent cascading failures.

## Constraints

### ✅ Do
- Implement "Zero-Trust Tooling": Verify every API call the agent tries to make.
- Use distinct identity/credentials for each agent to limit blast radius.
- Sanitize all content entering the agent's context (Memory Poisoning prevention).
- Treat "System Prompts" as sensitive code (protect them from leakage).
- Follow OWASP Top 10 for LLM Applications & Agentic AI (2025/2026).


### ❌ Don&#x27;t
- DO NOT give an agent direct, unrestricted `exec` or `run_shell_command` access without a sandbox.
- DO NOT let agents self-modify their own system prompts or code without strict review.
- DO NOT store secrets in the agent's context window / conversation history.


## Output Format
- `security_policy.json`: Defining allowed tools and scopes for the agent.
- `system_prompt_hardening_checklist.md`.

## Dependencies
- `../conducting-security-audit/SKILL.md`
