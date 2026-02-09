---
name: scaffolding-frontend
description: Initialize a Vite + React + TypeScript project with standardized directory structure, tooling, and configuration.
---

# Scaffolding Frontend

## Goal

Set up a new frontend project using Vite, React, and TypeScript with a production-ready directory structure, path aliases, linting, formatting, and essential dependencies pre-configured.

## When to Use

- Starting a brand-new frontend application
- Migrating an existing project to the Vite + React + TypeScript stack
- Resetting a project that has drifted from the standard structure

## Instructions

### 1. Initialize the Project

```bash
npm create vite@latest -- --template react-ts
cd <project-name>
npm install
```

### 2. Install Essential Dependencies

```bash
npm install react-router-dom zustand @tanstack/react-query
npm install -D @tanstack/eslint-plugin-query prettier eslint-config-prettier
```

### 3. Create Directory Structure

```bash
mkdir -p src/{components/ui,components/features,pages,hooks,services,stores,types,utils,styles}
```

### 4. Configure Path Aliases

Update `tsconfig.json` to add path aliases:

```json
{
  "compilerOptions": {
    "strict": true,
    "baseUrl": ".",
    "paths": {
      "@/*": ["src/*"]
    }
  }
}
```

Update `vite.config.ts` with aliases and a dev proxy:

```typescript
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 3000,
    proxy: {
      "/api": {
        target: "http://localhost:8080",
        changeOrigin: true,
      },
    },
  },
});
```

### 5. Configure ESLint and Prettier

Create `.prettierrc`:

```json
{
  "semi": true,
  "singleQuote": false,
  "trailingComma": "all",
  "printWidth": 100,
  "tabWidth": 2
}
```

Extend ESLint config to include Prettier and TanStack Query rules:

```javascript
// eslint.config.js
import js from "@eslint/js";
import tseslint from "typescript-eslint";
import reactHooks from "eslint-plugin-react-hooks";
import prettier from "eslint-config-prettier";

export default tseslint.config(
  js.configs.recommended,
  ...tseslint.configs.strict,
  prettier,
  {
    plugins: { "react-hooks": reactHooks },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "@typescript-eslint/no-unused-vars": ["error", { argsIgnorePattern: "^_" }],
    },
  },
);
```

### 6. Set Up Root Component

```typescript
// src/App.tsx
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 5 * 60 * 1000, retry: 1 },
  },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        {/* Route definitions go here */}
      </BrowserRouter>
    </QueryClientProvider>
  );
}
```

## Constraints

### ✅ Do
- Use strict TypeScript (`"strict": true` in tsconfig)
- Configure path aliases (`@/` maps to `src/`)
- Set up a dev proxy in `vite.config.ts` for API calls
- Keep all source code inside `src/`
- Pin major dependency versions in `package.json`


### ❌ Don&#x27;t
- Eject from Vite or modify internal Vite/Rollup internals
- Use Create React App (CRA) -- it is deprecated
- Skip TypeScript strict mode
- Install CSS-in-JS libraries unless explicitly required
- Commit `.env` files containing secrets


## Output Format

A fully initialized project directory with:
- Working `npm run dev` / `npm run build` commands
- All directories under `src/` created and empty (with `.gitkeep` if needed)
- Path aliases verified with a sample import

## Dependencies

- [../../shared/environment-config/SKILL.md](../../shared/environment-config/SKILL.md) -- for environment variable conventions
- [references/project-structures.md](references/project-structures.md) -- canonical directory layout reference
