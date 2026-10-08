import { defineConfig, globalIgnores } from 'eslint/config'
import nextVitals from 'eslint-config-next/core-web-vitals'
import nextTs from 'eslint-config-next/typescript'

export default defineConfig([
  ...nextVitals,
  ...nextTs,
  {
    rules: {
      '@typescript-eslint/no-unused-vars': ['warn', { argsIgnorePattern: '^_' }],
      '@typescript-eslint/no-explicit-any': 'warn',
      'react/no-unescaped-entities': 'off',
      // React Compiler advisory rules (eslint-plugin-react-hooks v7). The app
      // does not use the React Compiler; these flag pre-existing patterns
      // (data loading via setState in effects, effects calling loaders
      // declared later in the component) that are correct at runtime.
      // Kept visible as warnings to burn down incrementally.
      'react-hooks/set-state-in-effect': 'warn',
      'react-hooks/immutability': 'warn',
    },
  },
  globalIgnores(['.next/**', 'out/**', 'build/**', 'node_modules/**', 'next-env.d.ts']),
])
