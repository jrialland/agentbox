import "@mantine/core/styles.css";
import "@mantine/notifications/styles.css";
import "@fontsource/silkscreen/400.css";
import "@fontsource/inter/400.css";
import "@fontsource/inter/500.css";
import "@fontsource/inter/600.css";
import "@fontsource/jetbrains-mono/400.css";
import "@fontsource/jetbrains-mono/500.css";
import "./design-system/styles/layers.css";
import "./design-system/tokens/tokens.css";
import "./design-system/styles/legacy.css";
import "./design-system/styles/global.css";

import React from "react";
import ReactDOM from "react-dom/client";

import { App } from "./App";

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
