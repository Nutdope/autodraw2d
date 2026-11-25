import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { port: 5173 },
  build: {
    // The only large chunk is three.js (~845 kB / ~227 kB gzip) for the 3D preview.
    // It is lazy-loaded after a part opens, so it never delays the first paint;
    // the main bundle stays ~190 kB.
    chunkSizeWarningLimit: 900,
  },
});
