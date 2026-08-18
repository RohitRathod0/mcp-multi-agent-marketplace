import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Reasoning: Minimal Vite config — React plugin only. The orchestrator API URL is
// read from VITE_API_URL at runtime (see src/api.ts) so this stays environment-agnostic.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
  },
});
