// ESLint for the QA suite (Playwright specs run in Node).
import js from "@eslint/js";
import tseslint from "typescript-eslint";
import globals from "globals";

export default tseslint.config(
  { ignores: ["node_modules/**", "test-results/**", "playwright-report/**", ".lighthouseci/**"] },
  js.configs.recommended,
  ...tseslint.configs.strict,
  { languageOptions: { globals: globals.node } },
);
