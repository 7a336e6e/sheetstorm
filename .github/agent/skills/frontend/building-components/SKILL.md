---
name: building-components
description: Build React components with TypeScript, composition patterns, and consistent structure.
---

# Building Components

## Goal

Create well-typed, reusable React function components following composition-first patterns with co-located types, tests, and styles.

## When to Use

- Building any new React component (primitive, composite, or page-level)
- Refactoring an existing component to improve type safety or composability
- Reviewing component code for adherence to project conventions

## Instructions

### 1. Component File Structure

Co-locate the component, its types, tests, and barrel export in a single directory:

```
Button/
├── Button.tsx           # Component implementation
├── Button.test.tsx      # Tests
└── index.ts             # Re-export: export { Button } from "./Button";
```

### 2. Define Props with TypeScript Interfaces

Always use `interface` for component props. Extend native HTML attributes when wrapping primitives:

```typescript
import { forwardRef, type ButtonHTMLAttributes } from "react";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "ghost";
  size?: "sm" | "md" | "lg";
  isLoading?: boolean;
}
```

### 3. Implement Function Components

Use named function declarations. Forward refs on all primitives:

```typescript
const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ variant = "primary", size = "md", isLoading = false, children, className, ...rest }, ref) => {
    const baseStyles = "inline-flex items-center justify-center rounded font-medium transition";
    const variantStyles: Record<NonNullable<ButtonProps["variant"]>, string> = {
      primary: "bg-blue-600 text-white hover:bg-blue-700",
      secondary: "bg-gray-200 text-gray-900 hover:bg-gray-300",
      ghost: "bg-transparent text-gray-700 hover:bg-gray-100",
    };
    const sizeStyles: Record<NonNullable<ButtonProps["size"]>, string> = {
      sm: "px-3 py-1.5 text-sm",
      md: "px-4 py-2 text-base",
      lg: "px-6 py-3 text-lg",
    };

    return (
      <button
        ref={ref}
        className={`${baseStyles} ${variantStyles[variant]} ${sizeStyles[size]} ${className ?? ""}`}
        disabled={isLoading || rest.disabled}
        {...rest}
      >
        {isLoading ? <span className="animate-spin mr-2">...</span> : null}
        {children}
      </button>
    );
  },
);

Button.displayName = "Button";
export { Button };
```

### 4. Composition Over Configuration

Prefer composing small components over adding many props to one component:

```typescript
// Good: composable
<Card>
  <Card.Header>
    <Card.Title>Dashboard</Card.Title>
  </Card.Header>
  <Card.Body>{content}</Card.Body>
</Card>

// Avoid: prop-heavy
<Card title="Dashboard" headerAction={<Button />} body={content} footer={footer} />
```

### 5. Component Categories

| Category    | Location                  | Purpose                              |
|-------------|---------------------------|--------------------------------------|
| Primitives  | `components/ui/`          | Button, Input, Card, Modal           |
| Composites  | `components/features/`    | UserCard, InvoiceTable, SearchBar    |
| Pages       | `pages/`                  | DashboardPage, SettingsPage          |

### 6. Separate Concerns

Keep data fetching out of presentational components. Pass data through props:

```typescript
// Page fetches, component renders
function UsersPage() {
  const { data: users } = useQuery({ queryKey: ["users"], queryFn: fetchUsers });
  return <UserList users={users ?? []} />;
}

// Pure presentational component
interface UserListProps {
  users: User[];
}

function UserList({ users }: UserListProps) {
  return (
    <ul>
      {users.map((user) => (
        <li key={user.id}>{user.name}</li>
      ))}
    </ul>
  );
}
```

## Constraints

### ✅ Do
- Give each component a single responsibility
- Define explicit prop types using `interface`
- Use `forwardRef` on all primitive UI components
- Use composition (children, compound components) for flexibility
- Co-locate component, types, and tests in the same directory
- Use Tailwind utility classes for styling


### ❌ Don&#x27;t
- Use `any` or `unknown` for prop types
- Prop-drill more than 2 levels deep -- lift state or use a store
- Mix data fetching logic into presentational components
- Hardcode user-facing strings (prepare for i18n)
- Use class components
- Create "god components" with more than 200 lines


## Output Format

A component directory containing:
- `ComponentName.tsx` with typed props and implementation
- `index.ts` barrel export
- `ComponentName.test.tsx` placeholder or full tests

## Dependencies

- [frontend/scaffolding-frontend/SKILL.md](../scaffolding-frontend/SKILL.md) -- project must be scaffolded first
- [references/component-patterns.md](references/component-patterns.md) -- advanced pattern reference
