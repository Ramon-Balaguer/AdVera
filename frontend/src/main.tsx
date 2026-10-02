import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import { ApiHealthGate } from "./ApiHealthGate";
import { App } from "./App";
import "@fontsource-variable/geist";
import "./styles.css";
import "./theme.css";

const queryClient = new QueryClient();

// The gate stays outside StrictMode to avoid duplicate startup requests in development.
createRoot(document.getElementById("root")!).render(
  <ApiHealthGate>
    <StrictMode>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </QueryClientProvider>
    </StrictMode>
  </ApiHealthGate>,
);
