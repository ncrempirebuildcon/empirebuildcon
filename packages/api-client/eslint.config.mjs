// ESLint for @empire/api-client. The generated schema is excluded: it is never hand-edited.
import js from "@eslint/js";
import tseslint from "typescript-eslint";
import globals from "globals";

export default tseslint.config(
  { ignores: ["node_modules/**", "src/schema.d.ts"] },
  js.configs.recommended,
  ...tseslint.configs.strict,
  {
    // Build scripts run in Node.
    files: ["scripts/**/*.mjs"],
    languageOptions: { globals: globals.node },
  },
);
