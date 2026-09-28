import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { GlossaryProvider } from "./components/Glossary";
import "./styles.css";

createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    {/* Above App because the glossary panel lives in the sidebar while the chips that open it
        are spread through the workspace column. */}
    <GlossaryProvider>
      <App />
    </GlossaryProvider>
  </React.StrictMode>,
);
