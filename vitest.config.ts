import { defineConfig } from "vitest/config";

// Playwright owns e2e/ (run with `npm run test:e2e`); vitest runs only the unit tests.
export default defineConfig({
  test: { exclude: ["e2e/**", "node_modules/**", ".next/**", ".venv/**"] },
});
