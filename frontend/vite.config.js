import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  css: {
    preprocessorOptions: {
      scss: /** @type {import("vite").SassPreprocessorOptions} */ ({
        api: "modern-compiler",
        silenceDeprecations: ["legacy-js-api", "import"],
      }),
    },
  },
});