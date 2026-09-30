import { type FormEvent, type ReactNode, useEffect, useState } from "react";

// ADR 0019: when the API needs a shared token, ask for it once and exchange it for an
// HttpOnly session cookie. The token itself is never stored in the page or in localStorage.
type Access = "checking" | "open" | "required" | "authenticated";

export function AccessGate({ children }: { children: ReactNode }) {
  const [access, setAccess] = useState<Access>("checking");
  const [token, setToken] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/session", { cache: "no-store" })
      .then(async (response) => (response.ok ? ((await response.json()) as { access: Access }).access : "open"))
      .catch(() => "open" as Access)
      .then((value) => {
        if (!cancelled) setAccess(value);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const response = await fetch("/api/session", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token }),
      });
      if (response.ok) {
        setToken("");
        setAccess("authenticated");
      } else {
        setError(response.status === 401 ? "Token incorrecto." : "No se pudo iniciar la sesión.");
      }
    } catch {
      setError("No se pudo contactar con la API.");
    } finally {
      setBusy(false);
    }
  };

  if (access === "checking") return null;
  if (access !== "required") return <>{children}</>;

  return (
    <main className="startup">
      <h1>AdVera</h1>
      <form onSubmit={submit} className="access-form">
        <label>
          <span>Token de acceso</span>
          <input
            type="password"
            autoComplete="off"
            value={token}
            onChange={(event) => setToken(event.target.value)}
            autoFocus
          />
        </label>
        <button type="submit" disabled={!token || busy}>
          Entrar
        </button>
        {error && <p role="alert">{error}</p>}
      </form>
    </main>
  );
}
