import { useEffect, useState } from "react";
import { isAxiosError } from "axios";

import { getDatabaseStatus, type DatabaseHealth } from "../api/restaurant";

type StatusState =
  | { kind: "loading" }
  | { kind: "ready"; health: DatabaseHealth }
  | { kind: "error"; message: string };

export function DatabaseStatus() {
  const [state, setState] = useState<StatusState>({ kind: "loading" });

  useEffect(() => {
    let active = true;
    void getDatabaseStatus()
      .then((health) => active && setState({ kind: "ready", health }))
      .catch((error: unknown) => {
        if (!active) return;
        const message = isAxiosError(error)
          ? error.response?.data?.message ?? "Database connection is unavailable"
          : "Database connection is unavailable";
        setState({ kind: "error", message });
      });
    return () => {
      active = false;
    };
  }, []);

  if (state.kind === "loading") return <p className="status loading">Checking database…</p>;
  if (state.kind === "error") return <p className="status error">{state.message}</p>;
  return (
    <p className="status success">
      Database ready: {state.health.table_count} tables in {state.health.schema}
    </p>
  );
}
