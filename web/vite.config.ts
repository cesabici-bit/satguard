import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { viteStaticCopy } from "vite-plugin-static-copy";

// Cesium static assets must be served alongside the app
const cesiumSource = "node_modules/cesium/Build/Cesium";

export default defineConfig({
  plugins: [
    react(),
    viteStaticCopy({
      targets: [
        { src: `${cesiumSource}/Workers/**/*`, dest: "cesium/Workers" },
        { src: `${cesiumSource}/ThirdParty/**/*`, dest: "cesium/ThirdParty" },
        { src: `${cesiumSource}/Assets/**/*`, dest: "cesium/Assets" },
        { src: `${cesiumSource}/Widgets/**/*`, dest: "cesium/Widgets" },
      ],
    }),
  ],
  define: {
    CESIUM_BASE_URL: JSON.stringify("/cesium"),
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
  build: {
    chunkSizeWarningLimit: 4000, // Cesium is large
  },
});
