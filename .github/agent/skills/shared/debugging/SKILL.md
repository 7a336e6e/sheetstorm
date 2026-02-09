---
name: Systematic Debugging
description: rigorous, evidence-based approach to identifying root causes of bugs using the Scientific Method (Hypothesis -> Experiment -> Conclusion).
---

# Systematic Debugging

## Goal
Identify the root cause of a bug through isolation and reproduction, NOT by guessing or randomly changing code.

## When to Use
- A test is failing.
- The application behaves unexpectedly.
- An error log appears in production.
- "It works on my machine" but fails elsewhere.

## Instructions

### 1. Reproduce
Create a minimal reproduction case.
- **Script**: Write a standalone script (e.g., `repro.py`) that triggers the bug.
- **Test**: Write a failing test case in the existing suite.
- **Input**: Identify the exact inputs (payload, env vars, user state) that cause the crash.

### 2. Isolate (Binary Search)
Narrow down the scope.
- **Code**: Comment out half the logic. Does it still fail?
- **Data**: Remove fields from the input. What is the minimum required payload?
- **Time**: When did it start failing? `git bisect` to find the bad commit.

### 3. Log & Trace
Don't stare at the code; look at the execution.
- **Print**: Add `print()` or `logger.info()` at key decision points.
- **Inspect**: Check variable values *immediately before* the crash.
- **Trace**: Follow the data flow across boundaries (API -> Controller -> Service -> DB).

### 4. Hypothesis & Experiment
Formulate a theory.
- "I think the user ID is null because the session middleware failed."
- **Experiment**: Log the user ID in the middleware.
- **Result**: Validates or rejects the hypothesis.

## Constraints

### ✅ Do
- **DO**: Create a reproduction script/test *before* changing any implementation code.
- **DO**: Use `git bisect` if the bug is a regression.
- **DO**: Verify the fix by running the reproduction script again (it should pass).
- **DO**: Remove all temporary debug logging before committing the fix.

### ❌ Don't
- **DON'T**: Guess or "shotgun" fixes (changing random lines hoping it works).
- **DON'T**: Say "I fixed it" without seeing the reproduction case pass.
- **DON'T**: Ignore error messages; read the *entire* stack trace.

## Output Format
- `repro_bug_name.py` (or similar).
- `DEBUG_LOG.md` (optional, for tracking complex investigations).

## Dependencies
- `shared/task-tracking/SKILL.md` -- Log the bug and findings.
