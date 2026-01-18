import { defineConfig } from "vite";
import react from "@vitejs/plugin-react-swc";
import path from "path";
import { fileURLToPath } from "url";
import { gitChangelogPlugin } from "./vite-plugin-git-changelog";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react(), gitChangelogPlugin()],
  server: {
    host: "0.0.0.0", // all hosts
    port: 9200,
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
      components: path.resolve(__dirname, "./src/components"),
      assets: path.resolve(__dirname, "./src/assets"),
      styles: path.resolve(__dirname, "./src/styles"),
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: (id) => {
          // React ecosystem (React, Router, Query)
          if (
            id.includes("react") ||
            id.includes("react-dom") ||
            id.includes("react-router") ||
            id.includes("@tanstack/react-query")
          ) {
            return "vendor";
          }
          // Audio visualization libraries (Peaks.js, Konva, waveform-data)
          if (id.includes("peaks.js") || id.includes("waveform-data") || id.includes("konva")) {
            return "audio-viz";
          }
        },
      },
    },
  },
});
