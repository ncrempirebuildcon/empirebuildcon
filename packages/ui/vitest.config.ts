// Vitest setup for @empire/ui: jsdom so components can be rendered and their a11y attributes checked.
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "jsdom",
    globals: true,
    include: ["test/**/*.test.{ts,tsx}"],
  },
});
