import React from "react";

export function DataTable({ table, maxRows = 25 }) {
  if (!table || !table.columns || table.columns.length === 0) {
    return <div className="text-sm text-slate-400">No data to display.</div>;
  }
  const rows = table.rows || [];
  const shown = rows.slice(0, maxRows);
  const truncated = rows.length > maxRows;

  return (
    <div>
      <div className="table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              {table.columns.map((c) => (
                <th key={c}>{c}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {shown.map((row, i) => (
              <tr key={i}>
                {table.columns.map((c) => (
                  <td key={c} className={typeof row[c] === "number" ? "mono" : undefined}>
                    {row[c] == null ? "—" : formatCell(row[c])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mt-2 text-xs text-slate-400 dark:text-slate-500">
        {table.row_count != null ? `${table.row_count.toLocaleString()} rows total` : `${rows.length} rows`}
        {truncated ? ` · showing first ${maxRows}` : ""}
      </div>
    </div>
  );
}

function formatCell(v) {
  if (typeof v === "number") return v.toLocaleString(undefined, { maximumFractionDigits: 2 });
  if (Array.isArray(v)) return v.slice(0, 8).join(", ") + (v.length > 8 ? "…" : "");
  return String(v);
}
