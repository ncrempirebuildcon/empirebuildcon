/**
 * ESLint for the web app: Next.js core-web-vitals + TypeScript rules (handbook/CODE_STYLE.md §3).
 *
 * SECURITY: `react/no-danger` is an error everywhere except the JSON-LD helper, which escapes
 * its output (handbook/SECURITY.md §5). Do not add other exceptions.
 */
import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

export default defineConfig([
  ...nextVitals,
  ...nextTs,
  {
    rules: {
      "react/no-danger": "error",
      // react/no-danger only sees DOM elements; this also catches <Component dangerouslySetInnerHTML>
      // and createElement(..., { dangerouslySetInnerHTML }).
      "no-restricted-syntax": [
        "error",
        {
          selector:
            "JSXAttribute[name.name='dangerouslySetInnerHTML'], Property[key.name='dangerouslySetInnerHTML']",
          message:
            "Raw HTML is banned (SECURITY.md §5). Use the formatted-text renderer or JsonLd.",
        },
      ],
      "@typescript-eslint/no-explicit-any": "error",
    },
  },
  {
    files: ["src/components/JsonLd.tsx"],
    rules: { "react/no-danger": "off", "no-restricted-syntax": "off" },
  },
  globalIgnores([".next/**", "out/**", "build/**", "next-env.d.ts"]),
]);
