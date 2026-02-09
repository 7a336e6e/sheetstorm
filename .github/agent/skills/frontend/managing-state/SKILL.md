---
name: managing-state
description: Manage frontend state using Zustand for client state, TanStack Query for server state, and React Context for global static values.
---

# Managing State

## Goal

Choose the right state management tool for each category of state and implement typed, performant stores that minimize unnecessary re-renders.

## When to Use

- Adding new state to the application (decide where it lives)
- Migrating from Redux, MobX, or ad-hoc Context stores to Zustand + TanStack Query
- Optimizing re-renders caused by poorly scoped state

## Instructions

### 1. State Decision Tree

| Question                                     | Answer                     |
|----------------------------------------------|----------------------------|
| Does the data come from an API?              | TanStack Query             |
| Is it shared client state across pages?      | Zustand store              |
| Is it local to one component?                | `useState` / `useReducer`  |
| Is it global and rarely changes (theme, i18n)? | React Context            |

### 2. Zustand -- Client State

Create a typed store with selectors to prevent full-store re-renders:

```typescript
// stores/authStore.ts
import { create } from "zustand";
import { devtools, persist } from "zustand/middleware";

interface AuthState {
  token: string | null;
  user: { id: string; name: string } | null;
  setAuth: (token: string, user: AuthState["user"]) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>()(
  devtools(
    persist(
      (set) => ({
        token: null,
        user: null,
        setAuth: (token, user) => set({ token, user }),
        logout: () => set({ token: null, user: null }),
      }),
      { name: "auth-storage" },
    ),
  ),
);

// Selectors -- consume only the slice you need
export const useToken = () => useAuthStore((s) => s.token);
export const useCurrentUser = () => useAuthStore((s) => s.user);
```

### 3. TanStack Query -- Server State

Use queries for reads and mutations for writes. Invalidate related queries after mutations:

```typescript
// hooks/useUsers.ts
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getUsers, createUser } from "@/services/userService";
import type { User, CreateUserPayload } from "@/types/user";

export function useUsers() {
  return useQuery<User[]>({
    queryKey: ["users"],
    queryFn: getUsers,
    staleTime: 5 * 60 * 1000,
  });
}

export function useCreateUser() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: CreateUserPayload) => createUser(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["users"] });
    },
  });
}
```

### 4. Optimistic Updates

For mutations where instant feedback matters:

```typescript
export function useUpdateUser() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (user: User) => updateUser(user),
    onMutate: async (updatedUser) => {
      await queryClient.cancelQueries({ queryKey: ["users"] });
      const previous = queryClient.getQueryData<User[]>(["users"]);
      queryClient.setQueryData<User[]>(["users"], (old) =>
        old?.map((u) => (u.id === updatedUser.id ? updatedUser : u)),
      );
      return { previous };
    },
    onError: (_err, _user, context) => {
      queryClient.setQueryData(["users"], context?.previous);
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["users"] });
    },
  });
}
```

### 5. React Context -- Global Static Values

Use only for values that change infrequently and are needed throughout the tree:

```typescript
// contexts/ThemeContext.tsx
import { createContext, useContext, useState, type ReactNode } from "react";

type Theme = "light" | "dark";

interface ThemeContextValue {
  theme: Theme;
  toggle: () => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<Theme>("light");
  const toggle = () => setTheme((t) => (t === "light" ? "dark" : "light"));
  return (
    <ThemeContext.Provider value={{ theme, toggle }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme must be used within <ThemeProvider>");
  return ctx;
}
```

## Constraints

### ✅ Do
- Colocate state as close to its usage as possible
- Use Zustand selectors to subscribe to individual slices
- Invalidate TanStack Query caches after mutations
- Type all store state and actions explicitly
- Use `devtools` middleware in Zustand during development


### ❌ Don&#x27;t
- Put server/API data into Zustand -- use TanStack Query instead
- Use React Context for frequently changing values (causes full subtree re-renders)
- Create one monolithic global store -- split by domain
- Call `setState` directly from inside render (causes infinite loops)
- Forget to handle loading and error states for queries


## Output Format

- Zustand store files in `src/stores/` with exported selectors
- TanStack Query hooks in `src/hooks/` wrapping service functions
- Context providers in `src/contexts/` only for theme, locale, or similar

## Dependencies

- [frontend/scaffolding-frontend/SKILL.md](../scaffolding-frontend/SKILL.md) -- Zustand and TanStack Query must be installed
- [frontend/building-components/SKILL.md](../building-components/SKILL.md) -- components consume state via props or hooks
