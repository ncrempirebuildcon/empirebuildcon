// Vitest for @empire/web: unit tests of the CMS's pure rules (src/lib/**), run in Node. Screens
// and journeys are tested in the browser (qa/, Playwright); components in @empire/ui.
import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

export default defineConfig({
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
  test: { environment: "node", include: ["test/**/*.test.ts", "test/**/*.test.tsx"] },
});
