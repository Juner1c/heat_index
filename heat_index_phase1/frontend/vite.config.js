import { defineConfig } from "vite";
import tailwindcss from "@tailwindcss/vite";
import { fileURLToPath } from "node:url";

export default defineConfig({
  plugins: [tailwindcss()],
  resolve: { dedupe: ["react", "react-dom", "react-is", "recharts"] },
  server: { port: 5173, strictPort: true, proxy: { "/api": "http://127.0.0.1:8000" },
    fs: { allow: [fileURLToPath(new URL(".", import.meta.url)), fileURLToPath(new URL("../dashboard/components/recharts/frontend/src", import.meta.url))] } },
});
