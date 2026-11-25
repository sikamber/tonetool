import { MutationCache, QueryCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { isUnauthorized } from "./api/client";
import { App } from "./ui/App";
import "./index.css";

/** Any request that is refused for lack of a login sends the app back to the login page. */
function onError(error: unknown) {
  if (isUnauthorized(error)) void queryClient.invalidateQueries({ queryKey: ["session"] });
}

const queryClient: QueryClient = new QueryClient({
  queryCache: new QueryCache({ onError }),
  mutationCache: new MutationCache({ onError }),
  defaultOptions: { queries: { refetchOnWindowFocus: false, retry: false } },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
);
