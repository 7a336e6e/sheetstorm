---
name: testing-frontend
description: Implement comprehensive frontend testing using Vitest for unit/integration tests and React Testing Library for component interactions.
---

# Testing Frontend

## Goal
Ensure frontend reliability through a mix of unit tests for logic and integration tests for components, verifying behavior from the user's perspective.

## When to Use
- Creating new components.
- Implementing complex utility logic.
- Fixing bugs (write a regression test).

## Instructions

### 1. Setup Vitest & RTL
Ensure `vitest` and `@testing-library/react` are configured.

```typescript
// vite.config.ts
test: {
  globals: true,
  environment: 'jsdom',
  setupFiles: './src/test/setup.ts',
}
```

### 2. Component Testing
Test behavior, not implementation details. Query by accessible roles.

```tsx
// Button.test.tsx
import { render, screen, fireEvent } from '@testing-library/react';
import { Button } from './Button';
import { vi } from 'vitest';

test('calls onClick when clicked', () => {
  const handleClick = vi.fn();
  render(<Button onClick={handleClick}>Submit</Button>);

  const button = screen.getByRole('button', { name: /submit/i });
  fireEvent.click(button);

  expect(handleClick).toHaveBeenCalledTimes(1);
});
```

### 3. Testing Asynchronous Logic
Use `waitFor` or `findBy*` queries for async operations.

```tsx
test('displays user data after fetch', async () => {
  render(<UserProfile id="1" />);
  
  // Show loading first
  expect(screen.getByText(/loading/i)).toBeInTheDocument();

  // Wait for data
  const user = await screen.findByRole('heading', { name: /john doe/i });
  expect(user).toBeInTheDocument();
});
```

### 4. Mocking
Mock external modules and API calls using MSW (Mock Service Worker) or Vitest spies.
Prefer MSW for API mocking to test the full network stack.

## Constraints

### ✅ Do
- Prioritize testing user interactions (clicks, typing) over internal state.
- Use `screen.getByRole` as the primary query method (ensures accessibility).
- Mock network requests at the network layer (MSW) or API client layer, not the component layer.
- Run tests in CI before merging.
- Group tests with `describe` blocks matching the component/feature name.


### ❌ Don&#x27;t
- DO NOT test implementation details (e.g., checking if a specific CSS class exists or if a state variable changed).
- DO NOT use `getByTestId` unless no other query works.
- DO NOT use shallow rendering (Enzyme style). Render the full component tree.
- DO NOT ignore accessibility warnings in tests.


## Output Format
- `*.test.tsx` or `*.spec.ts` files alongside the source files.

## Dependencies
- `../building-components/SKILL.md`
- `../../designer/ensuring-accessibility/SKILL.md`
