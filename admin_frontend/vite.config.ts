import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: path.resolve(__dirname, "../static/game/admin/flowchart_editor"),
    emptyOutDir: true,
    rollupOptions: {
      input: path.resolve(__dirname, "src/main.tsx"),
      output: {
        // Single deterministic filenames for easy <script> inclusion
        entryFileNames: "index.js",
        chunkFileNames: "chunks/[name].js",
        assetFileNames: (info) =>
          info.name?.endsWith(".css") ? "index.css" : "assets/[name][extname]",
      },
    },
  },
});
