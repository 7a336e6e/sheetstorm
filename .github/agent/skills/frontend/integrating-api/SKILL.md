---
name: integrating-api
description: Implement a type-safe API client using TanStack Query and Axios/Fetch to handle data fetching, caching, and server state.
---

# Integrating API

## Goal
Establish a robust, type-safe communication layer between frontend and backend that handles loading states, errors, caching, and data synchronization seamlessly.

## When to Use
- Fetching data for a component.
- Submitting forms or performing mutations.
- Syncing server state with client UI.

## Instructions

### 1. Setup API Client
Create a configured Axios instance or Fetch wrapper.

```typescript
// src/lib/api.ts
import axios from 'axios';

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    // Handle global errors (401, 500)
    return Promise.reject(error);
  }
);
```

### 2. Create Typed Hooks (TanStack Query)
Abstract data fetching into custom hooks. Do not fetch directly in components.

```typescript
// src/features/users/api/useUser.ts
import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { User } from '@/types';

const getUser = async (id: string): Promise<User> => {
  const { data } = await api.get(`/users/${id}`);
  return data;
};

export const useUser = (id: string) => {
  return useQuery({
    queryKey: ['user', id],
    queryFn: () => getUser(id),
    enabled: !!id,
  });
};
```

### 3. Handle Mutations
Use `useMutation` for updates/creates.

```typescript
export const useCreateUser = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (newUser: CreateUserDto) => api.post('/users', newUser),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] });
    },
  });
};
```

### 4. Error & Loading States
Handle these explicitly in the UI.

```tsx
const { data, isLoading, error } = useUser(userId);

if (isLoading) return <Spinner />;
if (error) return <ErrorMessage message={error.message} />;
```

## Constraints

### ✅ Do
- Use TanStack Query (React Query) for all server state management.
- Define query keys as arrays (`['resource', id]`) for proper cache invalidation.
- Type all API responses using Zod or TypeScript interfaces.
- centralized API client configuration (base URL, interceptors).
- Handle 401 Unauthorized globally (e.g., redirect to login).


### ❌ Don&#x27;t
- DO NOT use `useEffect` for data fetching. It leads to race conditions and waterfall requests.
- DO NOT store server data in global client state (Redux/Zustand) unless absolutely necessary. Use the query cache.
- DO NOT hardcode API URLs in components.
- DO NOT ignore loading or error states.


## Output Format
- `src/lib/api.ts` (client setup)
- `src/features/*/api/*.ts` (hooks and fetchers)

## Dependencies
- `../../backend/building-api-routes/SKILL.md` (Defines the API contract)
- `../managing-state/SKILL.md`
