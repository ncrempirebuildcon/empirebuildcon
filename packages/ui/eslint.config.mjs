// ESLint for @empire/ui (handbook/CODE_STYLE.md §3). Type-aware rules stay off to keep lint fast.
import js from "@eslint/js";
import tseslint from "typescript-eslint";
import globals from "globals";
import reactHooks from "eslint-plugin-react-hooks";

export default tseslint.config(
  { ignores: ["node_modules/**", "src/tokens.ts"] },
  js.configs.recommended,
  ...tseslint.configs.strict,
  {
    plugins: { "react-hooks": reactHooks },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "@typescript-eslint/no-explicit-any": "error",
      // SECURITY.md §5: shared components never render raw HTML.
      "no-restricted-syntax": [
        "error",
        {
          selector:
            "JSXAttribute[name.name='dangerouslySetInnerHTML'], Property[key.name='dangerouslySetInnerHTML']",
          message: "Raw HTML is banned in shared components (SECURITY.md §5).",
        },
      ],
    },
  },
  {
    // Build scripts run in Node.
    files: ["scripts/**/*.mjs"],
    languageOptions: { globals: globals.node },
  },
);
