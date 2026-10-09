// Jest config for unit + component tests (see assets/docs/development.md).
//
// - `next/jest` wires the SWC transform, CSS/image mocks, `.env` loading and
//   the Next.js compiler options, so no Babel/ts-jest config is needed.
// - Default environment is jsdom (components, hooks, zustand stores). Pure
//   logic tests can opt into the faster node environment with a docblock at
//   the very top of the file:
//       /** @jest-environment node */
// - Tests live next to the code: src/**/*.test.ts(x). Playwright specs live in
//   e2e/ and are run by `npm run test:e2e`, never by Jest.
// CommonJS on purpose: Jest loads this file without a TS/ESM transform.
// eslint-disable-next-line @typescript-eslint/no-require-imports
const nextJest = require('next/jest')

const createJestConfig = nextJest({ dir: './' })

/** @type {import('jest').Config} */
const config = {
  testEnvironment: 'jsdom',
  setupFilesAfterEnv: ['<rootDir>/jest.setup.ts'],
  testMatch: ['<rootDir>/src/**/*.test.{ts,tsx}'],
  testPathIgnorePatterns: ['/node_modules/', '<rootDir>/.next/', '<rootDir>/e2e/'],
  moduleNameMapper: {
    '^@/(.*)$': '<rootDir>/src/$1',
  },
  // Reset call history between tests (implementations from jest.mock
  // factories are kept; use mockReset/mockRestore explicitly when needed).
  clearMocks: true,
}

module.exports = createJestConfig(config)
