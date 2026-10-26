import js from "@eslint/js";
import globals from "globals";
import html from "eslint-plugin-html";

const rules = {
  ...js.configs.recommended.rules,
  "no-unused-vars": ["error", { args: "after-used", caughtErrors: "none" }],
  "no-empty": ["error", { allowEmptyCatch: true }],
};

export default [
  { ignores: ["**/node_modules/**", "**/dist/**"] },
  {
    files: ["**/*.js", "**/*.mjs"],
    languageOptions: { ecmaVersion: "latest", sourceType: "commonjs", globals: globals.node },
    rules,
  },
  { files: ["**/*.mjs"], languageOptions: { sourceType: "module" } },
  {
    files: ["front/**/*.html"],
    plugins: { html },
    languageOptions: { ecmaVersion: "latest", sourceType: "script", globals: globals.browser },
    rules,
  },
];
