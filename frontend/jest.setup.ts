// Runs after the test framework is installed, before every test file.
// Shared by all WPs: add browser API shims here once instead of per test.
import '@testing-library/jest-dom'

// The shims below only apply to the jsdom environment; files that opt into
// `@jest-environment node` have no `window`.
if (typeof window !== 'undefined') {
  // Radix UI (popper, scroll-area) and React Flow observe element sizes.
  if (!('ResizeObserver' in window)) {
    class ResizeObserverStub {
      observe() {}
      unobserve() {}
      disconnect() {}
    }
    Object.defineProperty(window, 'ResizeObserver', { writable: true, configurable: true, value: ResizeObserverStub })
    Object.defineProperty(globalThis, 'ResizeObserver', { writable: true, configurable: true, value: ResizeObserverStub })
  }

  // jsdom has no matchMedia (used by responsive hooks / prefers-* queries).
  if (!window.matchMedia) {
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      configurable: true,
      value: (query: string) => ({
        matches: false,
        media: query,
        onchange: null,
        addListener: () => {},
        removeListener: () => {},
        addEventListener: () => {},
        removeEventListener: () => {},
        dispatchEvent: () => false,
      }),
    })
  }

  // Radix Select / DropdownMenu call these on pointer interaction.
  const proto = window.HTMLElement.prototype as unknown as Record<string, unknown>
  if (!proto.scrollIntoView) proto.scrollIntoView = () => {}
  if (!proto.hasPointerCapture) proto.hasPointerCapture = () => false
  if (!proto.releasePointerCapture) proto.releasePointerCapture = () => {}
}
