// Vite dev server and build. In development, /api/* is forwarded to the API on port 8000,
// so the browser sees one origin and no CORS setup is needed (nginx does the same in Docker).
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
