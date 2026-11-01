import { defineConfig } from "vitest/config";
export default defineConfig({
  server: { proxy: { "/api": "http://127.0.0.1:8000" } },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/setup.ts"],
    globals: true,
    exclude: ["e2e/**", "node_modules/**"],
  },
});
