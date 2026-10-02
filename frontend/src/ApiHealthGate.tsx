import { type ReactNode, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

// docs/features/frontend-api-health-gate.md: block the app until GET /api/health
// succeeds, retrying every five seconds on network errors or non-2xx responses.
export const HEALTH_RETRY_MS = 5000;

type GateState = "checking" | "starting" | "ready";

export function ApiHealthGate({ children }: { children: ReactNode }) {
  const [state, setState] = useState<GateState>("checking");
  const { t } = useTranslation();

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const check = async () => {
      try {
        const response = await fetch("/api/health", { cache: "no-store" });
        if (cancelled) return;
        if (response.ok) {
          setState("ready");
          return;
        }
      } catch {
        if (cancelled) return;
      }
      setState("starting");
      timer = setTimeout(check, HEALTH_RETRY_MS);
    };

    void check();
    return () => {
      cancelled = true;
      if (timer !== undefined) clearTimeout(timer);
    };
  }, []);

  if (state === "ready") return <>{children}</>;

  return (
    <main className="startup" role="status" aria-live="polite">
      <h1>AdVera</h1>
      <p>{state === "checking" ? t("startup.checking") : t("startup.starting")}</p>
    </main>
  );
}
