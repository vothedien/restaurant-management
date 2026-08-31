import { useEffect, useState } from "react";

import { getDiningTables, type DiningTable } from "../api/restaurant";

export function SalesDashboard() {
  const [tables, setTables] = useState<DiningTable[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    void getDiningTables()
      .then((items) => active && setTables(items))
      .catch(() => active && setError("Unable to load dining tables."))
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, []);

  return (
    <section>
      <p className="eyebrow">Sales</p>
      <h1>Dining tables</h1>
      {loading && <p>Loading tables…</p>}
      {error && <p className="status error">{error}</p>}
      {!loading && !error && (
        <div className="grid">
          {tables.map((table) => (
            <article className="panel" key={table.table_id}>
              <strong>{table.table_code}</strong>
              <p>{table.table_name ?? "Unnamed table"}</p>
              <span>{table.capacity} seats · {table.status}</span>
            </article>
          ))}
          {tables.length === 0 && <p>No tables found.</p>}
        </div>
      )}
    </section>
  );
}
