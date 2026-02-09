---
name: component-patterns
description: Reference for advanced React component patterns with TypeScript examples.
---

# Component Patterns

## Compound Components

A parent component provides shared state via context. Children consume that context,
enabling a flexible, declarative API:

```typescript
import { createContext, useContext, useState, type ReactNode } from "react";

// Context
interface TabsContextValue {
  activeTab: string;
  setActiveTab: (id: string) => void;
}

const TabsContext = createContext<TabsContextValue | null>(null);

function useTabsContext() {
  const ctx = useContext(TabsContext);
  if (!ctx) throw new Error("Tabs compound components must be used within <Tabs>");
  return ctx;
}

// Parent
interface TabsProps {
  defaultTab: string;
  children: ReactNode;
}

function Tabs({ defaultTab, children }: TabsProps) {
  const [activeTab, setActiveTab] = useState(defaultTab);
  return (
    <TabsContext.Provider value={{ activeTab, setActiveTab }}>
      <div role="tablist">{children}</div>
    </TabsContext.Provider>
  );
}

// Child: Tab trigger
interface TabProps {
  id: string;
  children: ReactNode;
}

function Tab({ id, children }: TabProps) {
  const { activeTab, setActiveTab } = useTabsContext();
  return (
    <button role="tab" aria-selected={activeTab === id} onClick={() => setActiveTab(id)}>
      {children}
    </button>
  );
}

// Child: Tab panel
interface PanelProps {
  id: string;
  children: ReactNode;
}

function Panel({ id, children }: PanelProps) {
  const { activeTab } = useTabsContext();
  if (activeTab !== id) return null;
  return <div role="tabpanel">{children}</div>;
}

// Attach sub-components
Tabs.Tab = Tab;
Tabs.Panel = Panel;

export { Tabs };
```

Usage:

```tsx
<Tabs defaultTab="general">
  <Tabs.Tab id="general">General</Tabs.Tab>
  <Tabs.Tab id="security">Security</Tabs.Tab>
  <Tabs.Panel id="general">General settings...</Tabs.Panel>
  <Tabs.Panel id="security">Security settings...</Tabs.Panel>
</Tabs>
```

## Controlled vs Uncontrolled Components

### Uncontrolled (internal state)

Use when the parent does not need to read or override the value:

```typescript
function SearchInput() {
  const [query, setQuery] = useState("");
  return <input value={query} onChange={(e) => setQuery(e.target.value)} />;
}
```

### Controlled (state lifted to parent)

Use when the parent needs to read, validate, or synchronize the value:

```typescript
interface SearchInputProps {
  value: string;
  onChange: (value: string) => void;
}

function SearchInput({ value, onChange }: SearchInputProps) {
  return <input value={value} onChange={(e) => onChange(e.target.value)} />;
}
```

### Hybrid pattern

Support both modes by detecting whether the `value` prop is provided:

```typescript
interface InputProps {
  value?: string;
  defaultValue?: string;
  onChange?: (value: string) => void;
}

function Input({ value, defaultValue = "", onChange }: InputProps) {
  const [internal, setInternal] = useState(defaultValue);
  const isControlled = value !== undefined;
  const currentValue = isControlled ? value : internal;

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!isControlled) setInternal(e.target.value);
    onChange?.(e.target.value);
  };

  return <input value={currentValue} onChange={handleChange} />;
}
```

## Render Props

Pass a function as a prop to give the consumer full control over what is rendered:

```typescript
interface ListProps<T> {
  items: T[];
  renderItem: (item: T, index: number) => ReactNode;
  keyExtractor: (item: T) => string;
}

function List<T>({ items, renderItem, keyExtractor }: ListProps<T>) {
  return (
    <ul>
      {items.map((item, index) => (
        <li key={keyExtractor(item)}>{renderItem(item, index)}</li>
      ))}
    </ul>
  );
}
```

Usage:

```tsx
<List
  items={users}
  keyExtractor={(u) => u.id}
  renderItem={(user) => <span>{user.name} ({user.email})</span>}
/>
```

## Higher-Order Components (HOCs)

HOCs wrap a component to inject props. Prefer custom hooks in most cases, but HOCs
are still useful for cross-cutting concerns like authorization gates:

```typescript
function withAuth<P extends object>(WrappedComponent: React.ComponentType<P>) {
  return function AuthenticatedComponent(props: P) {
    const { isAuthenticated } = useAuthStore();
    if (!isAuthenticated) return <Navigate to="/login" />;
    return <WrappedComponent {...props} />;
  };
}
```

**When to use HOCs vs hooks:**
- Use a **hook** when you need to share logic and the consumer controls the render.
- Use a **HOC** when you need to conditionally render the entire component (auth gates, feature flags).

## Custom Hook Extraction

Extract a custom hook when:
1. Logic is reused across two or more components.
2. A component's logic exceeds ~30 lines and is conceptually separable.
3. You want to test business logic independently from rendering.

```typescript
// hooks/useUsers.ts
import { useQuery } from "@tanstack/react-query";
import { getUsers } from "@/services/userService";
import type { User } from "@/types/user";

export function useUsers() {
  return useQuery<User[]>({
    queryKey: ["users"],
    queryFn: getUsers,
  });
}
```

```typescript
// components/features/UserList/UserList.tsx
import { useUsers } from "@/hooks/useUsers";

export function UserList() {
  const { data: users, isLoading, error } = useUsers();
  if (isLoading) return <Spinner />;
  if (error) return <ErrorMessage error={error} />;
  return (
    <ul>
      {users?.map((u) => <li key={u.id}>{u.name}</li>)}
    </ul>
  );
}
```
