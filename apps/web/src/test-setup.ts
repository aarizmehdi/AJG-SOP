import '@testing-library/jest-dom/vitest';

Object.defineProperty(window, 'matchMedia', {
  configurable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    addEventListener: () => {},
    removeEventListener: () => {},
  }),
});
Object.defineProperty(Element.prototype, 'scrollIntoView', {
  configurable: true,
  value: () => {},
});
