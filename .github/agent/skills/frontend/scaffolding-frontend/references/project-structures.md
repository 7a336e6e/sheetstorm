---
name: project-structures
description: Reference for React + TypeScript project directory layout and file naming conventions.
---

# Project Directory Structure

## Canonical Layout

```
src/
├── components/          # Reusable UI components
│   ├── ui/              # Primitives (Button, Input, Card, Modal)
│   └── features/        # Feature-specific components (UserAvatar, InvoiceTable)
├── pages/               # Route-level page components
├── hooks/               # Custom React hooks
├── services/            # API client functions
├── stores/              # Zustand stores
├── types/               # Shared TypeScript types and interfaces
├── utils/               # Pure utility functions
├── styles/              # Global styles, Tailwind config, CSS variables
└── App.tsx              # Root component with router and providers
```

## Directory Responsibilities

### `components/ui/`

Low-level, general-purpose primitives. These have no business logic and are styled
building blocks. Each component gets its own directory:

```
components/ui/
├── Button/
│   ├── Button.tsx
│   ├── Button.test.tsx
│   └── index.ts
├── Input/
│   ├── Input.tsx
│   ├── Input.test.tsx
│   └── index.ts
└── index.ts             # Barrel export
```

### `components/features/`

Components tied to a specific domain or feature. They may import from `ui/` and
from `hooks/` or `stores/`, but they should not import from `pages/`.

```
components/features/
├── UserAvatar/
│   ├── UserAvatar.tsx
│   └── index.ts
└── InvoiceTable/
    ├── InvoiceTable.tsx
    ├── InvoiceTableRow.tsx
    └── index.ts
```

### `pages/`

One file per route. Pages compose feature components and handle route params,
data loading, and layout.

```
pages/
├── HomePage.tsx
├── DashboardPage.tsx
├── SettingsPage.tsx
└── NotFoundPage.tsx
```

### `hooks/`

Custom hooks extracted from components when logic is reusable or complex.

```
hooks/
├── useDebounce.ts
├── useMediaQuery.ts
└── useLocalStorage.ts
```

### `services/`

Functions that communicate with external APIs. Each service module maps to an
API resource or domain.

```
services/
├── apiClient.ts         # Base fetch wrapper with auth
├── userService.ts       # getUsers, getUser, createUser, ...
└── invoiceService.ts    # getInvoices, createInvoice, ...
```

### `stores/`

Zustand stores for client-side state. One file per logical store.

```
stores/
├── authStore.ts
├── uiStore.ts
└── index.ts
```

### `types/`

Shared TypeScript interfaces and type aliases. Types specific to a single
component or service should live next to that file instead.

```
types/
├── user.ts
├── invoice.ts
└── api.ts               # Generic API response/error types
```

### `utils/`

Pure functions with no React dependency. Must be side-effect-free and easy to
unit test.

```
utils/
├── formatCurrency.ts
├── dateHelpers.ts
└── validators.ts
```

## File Naming Conventions

| Category        | Convention    | Example                  |
|-----------------|---------------|--------------------------|
| Components      | PascalCase    | `Button.tsx`             |
| Pages           | PascalCase    | `DashboardPage.tsx`      |
| Hooks           | camelCase     | `useDebounce.ts`         |
| Utilities       | camelCase     | `formatCurrency.ts`      |
| Services        | camelCase     | `userService.ts`         |
| Stores          | camelCase     | `authStore.ts`           |
| Types           | camelCase     | `user.ts`                |
| Test files      | match source  | `Button.test.tsx`        |
| Barrel exports  | `index.ts`    | `index.ts`               |

## Import Order Convention

Imports within a file should follow this order, separated by blank lines:

1. React / third-party libraries
2. `@/` aliased internal imports
3. Relative imports
4. Type-only imports

```typescript
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { Button } from "@/components/ui";
import { useAuthStore } from "@/stores/authStore";

import { UserAvatar } from "./UserAvatar";

import type { User } from "@/types/user";
```
