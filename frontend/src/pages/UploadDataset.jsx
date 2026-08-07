import React, { useCallback, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";

import { StatCard } from "../components/StatCard.jsx";
import { api } from "../services/api.js";
import { useApp } from "../context/AppContext.jsx";

export default function UploadDataset() {
  const { refreshDatasets, selectDataset, setError } = useApp();
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [profile, setProfile] = useState(null);
  const [fileInfo, setFileInfo] = useState(null);
  const fileInput = useRef(null);

  const upload = useCallback(
    async (file) => {
      if (!file) return;
      setUploading(true);
      setFileInfo({ name: file.name, size: file.size });
      try {
        const data = await api.uploadDataset(file);
        setProfile(data.profile);
        selectDataset(data.dataset_id);
        await refreshDatasets();
        setError(null);
      } catch (e) {
        setError(e.message);
      } finally {
        setUploading(false);
      }
    },
    [refreshDatasets, selectDataset, setError]
  );

  const onDrop = (e) => {
    e.preventDefault();
    setDragging(false);
    const f = e.dataTransfer.files?.[0];
    if (f) upload(f);
  };

  const formats = ["csv", "xlsx", "xls"];
  const ext = (fileInfo?.name || "").split(".").pop()?.toLowerCase() || "";

  return (
    <div className="mx-auto max-w-5xl">
      <header className="mb-6">
        <h1 className="page-title">Upload Dataset</h1>
        <p className="page-sub">CSV and Excel files are automatically profiled by the Dataset Intelligence Agent.</p>
      </header>

      <motion.div
        whileHover={{ scale: dragging ? 1 : 1.005 }}
        onClick={() => fileInput.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={`flex cursor-pointer flex-col items-center justify-center rounded-3xl border-2 border-dashed p-12 text-center transition-all ${
          dragging
            ? "scale-[1.01] border-brand-500 bg-brand-50 dark:bg-brand-500/10"
            : "border-slate-300 bg-white/50 hover:border-brand-400 dark:border-slate-700 dark:bg-slate-900/40"
        }`}
      >
        <div className="text-5xl">📄</div>
        <div className="mt-3 text-lg font-bold text-slate-800 dark:text-slate-200">
          {uploading ? "Profiling dataset…" : "Drop a CSV or Excel file here"}
        </div>
        <div className="mt-1 text-sm text-slate-400">or click to browse · auto-detects dates, metrics, and column types</div>
        <input
          ref={fileInput}
          type="file"
          accept=".csv,.txt,.xlsx,.xls"
          className="hidden"
          onChange={(e) => upload(e.target.files?.[0])}
        />
        {fileInfo && (
          <div className="mt-4">
            <span className={`chip ${formats.includes(ext) ? "chip-success" : "chip-danger"}`}>
              {fileInfo.name} · {(fileInfo.size / 1024).toFixed(1)} KB
            </span>
          </div>
        )}
      </motion.div>

      {uploading && (
        <div className="glass card-pad mt-4 flex items-center justify-center gap-3">
          <span className="h-4 w-4 animate-spin rounded-full border-2 border-brand-500 border-t-transparent" />
          Running the Dataset Intelligence Agent…
        </div>
      )}

      {profile && !uploading && (
        <div className="mt-5">
          <div className="mb-4 grid grid-cols-2 gap-4 sm:grid-cols-3">
            <StatCard label="Rows" value={profile.rows.toLocaleString()} />
            <StatCard label="Columns" value={profile.columns} />
            <StatCard label="Missing values" value={profile.missing_total.toLocaleString()} tone={profile.missing_total > 0 ? "warning" : "success"} />
            <StatCard label="Duplicate rows" value={profile.duplicate_rows.toLocaleString()} tone={profile.duplicate_rows > 0 ? "warning" : "success"} />
            <StatCard label="Memory usage" value={profile.memory_usage} />
            <StatCard label="Date columns" value={profile.date_columns.length} tone={profile.date_columns.length ? "success" : "warning"} />
          </div>

          <div className="grid gap-5 lg:grid-cols-2">
            <div className="glass card-pad">
              <div className="card-title">Possible business metrics</div>
              <div className="mt-2 flex flex-wrap gap-2">
                {profile.possible_metrics.map((m) => (
                  <span key={m} className="chip chip-accent">{m}</span>
                ))}
                {profile.possible_metrics.length === 0 && (
                  <span className="text-xs text-slate-400">No numeric metric columns detected.</span>
                )}
              </div>
              <div className="card-title mt-4">Categorical dimensions</div>
              <div className="mt-2 flex flex-wrap gap-2">
                {profile.categorical_columns.map((m) => (
                  <span key={m} className="chip">{m}</span>
                ))}
                {profile.categorical_columns.length === 0 && (
                  <span className="text-xs text-slate-400">None detected.</span>
                )}
              </div>
            </div>

            <div className="glass card-pad">
              <div className="card-title">Column types</div>
              <div className="table-wrap mt-3">
                <table className="data-table">
                  <thead>
                    <tr><th>Column</th><th>Type</th><th>Category</th><th>Missing %</th></tr>
                  </thead>
                  <tbody>
                    {profile.column_profiles.slice(0, 12).map((c) => (
                      <tr key={c.name}>
                        <td className="mono">{c.name}</td>
                        <td>{c.dtype}</td>
                        <td><span className="chip">{c.category}</span></td>
                        <td>{c.missing_pct}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          <div className="mt-5 flex flex-wrap gap-2">
            <Link to="/explorer" className="btn btn-primary">Open Dataset Explorer →</Link>
            <Link to="/analyst" className="btn btn-ghost">Ask a question →</Link>
          </div>
        </div>
      )}
    </div>
  );
}