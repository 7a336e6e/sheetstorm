---
name: Test Driven Development
description: Implement features using the Red-Green-Refactor cycle to ensure testability and correctness from the start.
---

# Test Driven Development (TDD)

## Goal
Write code that is proven to work the moment it is written, preventing regression and ensuring high design quality.

## When to Use
- Implementing complex business logic.
- Fixing a bug (write the failing test first).
- Creating utility functions or data transformations.
- NOT strictly required for boilerplate/scaffolding, but recommended.

## Instructions

### 1. Red (Write a Failing Test)
Write a test that defines the expected behavior.
- It must fail. If it passes, your test is broken or the feature already exists.
- **Compilation Error**: Even not compiling counts as "Red".

```python
def test_calculate_total():
    # We haven't written the function yet
    result = calculate_total([10, 20]) 
    assert result == 30
```

### 2. Green (Make it Pass)
Write the *minimum* amount of code to pass the test.
- Do not optimize.
- Do not worry about clean code yet.
- Hardcoding values is acceptable *if* it passes the specific test (you will generalize in the next step).

```python
def calculate_total(items):
    return sum(items)
```

### 3. Refactor (Clean Up)
Improve the code while keeping the test green.
- Rename variables.
- Extract functions.
- Optimize performance.
- Remove duplication.

### 4. Repeat
Add the next test case (e.g., `test_calculate_total_empty_list`) and repeat.

## Constraints

### ✅ Do
- **DO**: Run tests after every change.
- **DO**: Write only enough code to pass the *current* failing test.
- **DO**: Treat test code with the same quality standards as production code.

### ❌ Don't
- **DON'T**: Write the implementation first, then "backfill" tests.
- **DON'T**: Skip the "Red" phase. You must verify the test *can* fail.
- **DON'T**: Refactor while the test is failing. Get to Green first.

## Output Format
- Test files (`tests/unit/test_xyz.py`).
- Implementation files.

## Dependencies
- `backend/testing-flask/SKILL.md` OR `frontend/testing-frontend/SKILL.md`
