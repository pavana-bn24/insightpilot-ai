import React, { useCallback, useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";

import { AnalysisResult } from "../components/AnalysisResult.jsx";
import { api } from "../services/api.js";
import { exportReport } from "../services/exportUtils.js";
import { useApp } from "../context/AppContext.jsx";

export default function HistoryPage() {
  const { refreshHistory } = useApp();
  const [history, setHistory] = useState([]);
  const [selected, setSelected] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    const h = await api.history();
    setHistory(h);
    setLoading(false);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const remove = async (id) => {
    await api.deleteHistory(id);
    if (selected === id) setSelected(null);
    await load();
    await refreshHistory();
  };

  const selectedEntry = selected ? history.find((h) => h.id === selected) : null;

  return (
    <div className="mx-auto max-w-4xl">
      <header className="mb-6">
        <h1 className="page-title">History</h1>
        <p className="page-sub">
          {history.length} analyses recorded in this session · click an entry to replay the full pipeline.
        </p>
      </header>

      {loading && (
        <div className="glass card-pad flex items-center justify-center gap-3">
          <span className="h-4 w-4 animate-spin rounded-full border-2 border-brand-500 border-t-transparent" />
          Loading history…
        </div>
      )}

      {!loading && history.length === 0 && (
        <div className="glass card-pad text-center">
          <div className="text-4xl">↺</div>
          <div className="mt-2 text-base font-bold text-slate-800 dark:text-slate-200">No history yet</div>
          <p className="mt-1 text-sm text-slate-400">Run an analysis in the AI Analyst to see it here.</p>
        </div>
      )}

      <div className="space-y-3">
        <AnimatePresence>
          {history.map((h) => (
            <motion.div
              key={h.id}
              layout
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, x: -20 }}
              whileHover={{ x: 3 }}
              onClick={() => setSelected(h.id)}
              className="glass card-pad flex cursor-pointer items-center gap-3"
            >
              <span className="chip chip-accent">{h.intent}</span>
              <div className="min-w-0 flex-1">
                <div className="truncate text-sm font-semibold text-slate-800 dark:text-slate-200">{h.question}</div>
                <div className="truncate text-xs text-slate-400">
                  {h.filename} · {new Date(h.created_at).toLocaleString()} · {h.llm_mode} mode ·{" "}
                  {(h.confidence * 100).toFixed(0)}% confident
                </div>
              </div>
              <span className="chip">{h.answer_label}</span>
              <button
                className="btn btn-ghost btn-sm"
                onClick={(e) => { e.stopPropagation(); remove(h.id); }}
              >
                ✕
              </button>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>

      {selectedEntry && (
        <div className="glass card-pad mt-6">
          <div className="mb-3 flex items-center justify-between">
            <div className="card-title">{selectedEntry.question}</div>
            <div className="flex gap-2">
              <button
                className="btn btn-ghost btn-sm"
                onClick={() => exportReport(selectedEntry.result, "insightpilot-report.md")}
              >
                ⬇ Report
              </button>
              <button className="btn btn-ghost btn-sm" onClick={() => setSelected(null)}>Close</button>
            </div>
          </div>
          <AnalysisResult result={selectedEntry.result} />
        </div>
      )}
    </div>
  );
}