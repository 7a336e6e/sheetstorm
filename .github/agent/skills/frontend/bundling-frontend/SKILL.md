---
name: bundling-frontend
description: Configure Vite to build optimized production assets, handling code splitting, tree-shaking, and static asset management.
---

# Bundling Frontend

## Goal
Produce a highly optimized, minified set of static assets (JS, CSS, images) ready for deployment to a CDN or static host, with optimal caching strategies.

## When to Use
- Setting up the build pipeline.
- Optimizing application load time (LCP, TTI).
- Configuring environment-specific build variables.

## Instructions

### 1. Vite Configuration
Configure `vite.config.ts` for production builds.

```typescript
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  build: {
    target: 'esnext',
    sourcemap: false, // Disable for prod, enable for staging
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ['react', 'react-dom', 'react-router-dom'],
          // Split heavy libs into their own chunks
        },
      },
    },
  },
});
```

### 2. Environment Variables
Use `.env` files for build-time configuration.

- `.env.development`: API endpoints for local dev.
- `.env.production`: API endpoints for prod.

Access them via `import.meta.env.VITE_API_URL`.

### 3. Asset Optimization
- **Images**: Use modern formats (WebP/AVIF). Vite handles imports automatically.
- **Fonts**: Self-host fonts when possible or use a performant CDN.
- **SVGs**: Import as components using plugin like `vite-plugin-svgr` or strictly as URLs.

### 4. Build Scripts
Ensure `package.json` has standard scripts:

```json
"scripts": {
  "dev": "vite",
  "build": "tsc && vite build",
  "preview": "vite preview"
}
```
Always run `tsc` (TypeScript Compiler) before `vite build` to catch type errors that Vite (using esbuild) ignores.

## Constraints

### ✅ Do
- Prefix all public environment variables with `VITE_`.
- Run type checking (`tsc`) before the build step.
- Use `manualChunks` to split large vendor libraries if the main bundle exceeds 500kb.
- Configure clean build output directories (`emptyOutDir: true`).
- Use path aliases (`@/components`) to simplify imports and refactoring.


### ❌ Don&#x27;t
- DO NOT include secrets (private API keys) in client-side bundles. They are visible to everyone.
- DO NOT rely on default browser caching for `index.html`; ensure the server sets `Cache-Control: no-cache`.
- DO NOT leave `sourcemap: true` in production unless you have a private error reporting service.
- DO NOT import unused heavy libraries (e.g., all of lodash). Import specific functions.


## Output Format
- `dist/` folder containing `index.html`, `assets/*.js`, `assets/*.css`.
- `vite.config.ts` configuration.

## Dependencies
- `../scaffolding-frontend/SKILL.md`
