import React from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";

import { DataTable } from "../components/DataTable.jsx";
import { StatCard } from "../components/StatCard.jsx";
import { useApp } from "../context/AppContext.jsx";

const CATEGORY_TONE = {
  numeric: "chip-accent",
  categorical: "chip-success",
  datetime: "chip-warning",
  text: "chip",
  id: "chip",
  boolean: "chip",
};

export default function DatasetExplorer() {
  const { datasets, activeDatasetId, activeProfile, selectDataset } = useApp();

  const header = (
    <header className="mb-6">
      <h1 className="page-title">Dataset Explorer</h1>
      <p className="page-sub">The Dataset Intelligence Agent profiles every upload automatically.</p>
      {datasets.length === 0 && (
        <Link to="/upload" className="btn btn-primary mt-3">Upload a dataset</Link>
      )}
    </header>
  );

  if (!activeProfile) {
    return (
      <div className="mx-auto max-w-5xl">
        {header}
        <div className="glass card-pad text-center">
          <div className="text-4xl">🗃️</div>
          <div className="mt-2 text-base font-bold text-slate-800 dark:text-slate-200">No dataset selected</div>
          <p className="mt-1 text-sm text-slate-400">Upload a CSV/Excel file or select a sample dataset.</p>
          <div className="mt-4 flex justify-center gap-2">
            <Link to="/upload" className="btn btn-primary">Upload dataset</Link>
          </div>
        </div>
      </div>
    );
  }

  const p = activeProfile;

  return (
    <div className="mx-auto max-w-6xl">
      {header}

      <div className="glass card-pad mb-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="text-base font-bold text-slate-900 dark:text-white">{p.filename}</div>
            <div className="mono text-xs text-slate-400">{p.dataset_id}</div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <select
              className="select w-60"
              value={activeDatasetId}
              onChange={(e) => selectDataset(e.target.value)}
            >
              <option value="" disabled>Choose dataset…</option>
              {datasets.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.filename} {d.sample ? "(sample)" : `(${d.rows ?? "?"} rows)`}
                </option>
              ))}
            </select>
            <Link to="/analyst" className="btn btn-primary btn-sm">Analyze →</Link>
          </div>
        </div>
      </div>

      <div className="mb-5 grid grid-cols-2 gap-4 lg:grid-cols-3">
        <StatCard label="Rows" value={p.rows.toLocaleString()} />
        <StatCard label="Columns" value={p.columns} />
        <StatCard label="Quality score" value={p.quality_score != null ? `${p.quality_score}/100` : "—"} tone={p.quality_score >= 80 ? "success" : p.quality_score >= 50 ? "warning" : "danger"} hint="data-quality heuristic" />
        <StatCard label="Date columns" value={p.date_columns.length} tone={p.date_columns.length ? "success" : "warning"} />
        <StatCard label="Missing values" value={p.missing_total.toLocaleString()} tone={p.missing_total ? "warning" : "success"} />
        <StatCard label="Duplicates" value={p.duplicate_rows.toLocaleString()} tone={p.duplicate_rows ? "warning" : "success"} />
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <div className="glass card-pad">
          <div className="card-title">Column profiles</div>
          <div className="table-wrap mt-3">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Column</th><th>Type</th><th>Category</th>
                  <th>Unique</th><th>Missing</th><th>Mean</th><th>Min</th><th>Max</th>
                </tr>
              </thead>
              <tbody>
                {p.column_profiles.map((c) => (
                  <tr key={c.name}>
                    <td className="mono text-brand-500 dark:text-brand-400">{c.name}</td>
                    <td>{c.dtype}</td>
                    <td><span className={`chip ${CATEGORY_TONE[c.category] || "chip"}`}>{c.category}</span></td>
                    <td>{c.unique ?? "—"}</td>
                    <td>{c.missing ?? 0}</td>
                    <td className="mono">{c.mean != null ? c.mean.toLocaleString(undefined, { maximumFractionDigits: 2 }) : "—"}</td>
                    <td className="mono">{c.min ?? "—"}</td>
                    <td className="mono">{c.max ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="space-y-5">
          <div className="glass card-pad">
            <div className="card-title">Preview (first rows)</div>
            <div className="mt-3">
              <DataTable table={{ columns: p.sample_columns, rows: p.head, row_count: p.rows }} maxRows={8} />
            </div>
          </div>
          <div className="glass card-pad">
            <div className="card-title">Business metrics</div>
            <div className="mt-2 flex flex-wrap gap-2">
              {(p.business_metrics || []).map((m, i) => (
                <span key={i} className="chip chip-accent" title={`${m.aggregate} of ${m.column}`}>
                  {m.label} ({m.column})
                </span>
              ))}
              {!(p.business_metrics || []).length && (
                <span className="text-xs text-slate-400">No KPI-style metrics detected.</span>
              )}
            </div>
            <div className="card-title mt-4">Detected date columns</div>
            <div className="mt-2 flex flex-wrap gap-2">
              {p.date_columns.length ? (
                p.date_columns.map((c) => <span key={c} className="chip chip-warning">{c}</span>)
              ) : (
                <span className="text-xs text-slate-400">None — trend & growth questions need a date column.</span>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}