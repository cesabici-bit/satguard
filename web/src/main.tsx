import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { Ion } from "cesium";
import App from "./App";

// Disable Cesium Ion — we use OpenStreetMap imagery (no token needed)
Ion.defaultAccessToken = "";

// Set Cesium static asset base URL (defined in vite.config.ts)
window.CESIUM_BASE_URL = CESIUM_BASE_URL;

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>
);
