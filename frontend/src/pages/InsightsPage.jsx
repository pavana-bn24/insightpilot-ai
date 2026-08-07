import React, { useEffect, useState } from "react";
import { motion } from "framer-motion";

import { AnalysisResult } from "../components/AnalysisResult.jsx";
import { api } from "../services/api.js";

export default function InsightsPage() {
  const [history, setHistory] = useState([]);
  const [selected, setSelected] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      const h = await api.history();
      setHistory(h);
      setLoading(false);
    })();
  }, []);

  const withInsight = history.filter((h) => h.insight);
  const selectedEntry = selected ? history.find((h) => h.id === selected) : null;

  return (
    <div className="mx-auto max-w-6xl">
      <header className="mb-6">
        <h1 className="page-title">Insights</h1>
        <p className="page-sub">Every answer the agent produced, distilled into business insights and recommendations.</p>
      </header>

      {loading && (
        <div className="glass card-pad flex items-center justify-center gap-3">
          <span className="h-4 w-4 animate-spin rounded-full border-2 border-brand-500 border-t-transparent" />
          Loading insights…
        </div>
      )}

      {!loading && withInsight.length === 0 && (
        <div className="glass card-pad text-center">
          <div className="text-4xl">💡</div>
          <div className="mt-2 text-base font-bold text-slate-800 dark:text-slate-200">No insights yet</div>
          <p className="mt-1 text-sm text-slate-400">Ask the AI Analyst a question to generate insights.</p>
        </div>
      )}

      <div className="grid gap-5 md:grid-cols-2">
        {withInsight.map((h, idx) => (
          <motion.div
            key={h.id}
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: idx * 0.03 }}
            className="glass card-pad"
          >
            <div className="flex items-center justify-between">
              <span className="chip">{h.intent}</span>
              <span className="chip chip-success">{(h.confidence * 100).toFixed(0)}%</span>
            </div>
            <div className="mt-2 text-sm font-semibold text-slate-800 dark:text-slate-200">{h.question}</div>
            <div className="mt-2 text-xs leading-relaxed text-slate-500 dark:text-slate-400">{h.insight}</div>
            {h.recommendation && (
              <div className="mt-3">
                <span className="chip chip-accent">Recommendation</span>
                <p className="mt-1.5 text-xs leading-relaxed text-slate-400">{h.recommendation}</p>
              </div>
            )}
            <div className="mt-4 flex items-center justify-between">
              <span className="mono text-xs text-slate-400">{h.answer_label} = {h.answer_value}</span>
              <button className="btn btn-ghost btn-sm" onClick={() => setSelected(h.id)}>Full report</button>
            </div>
          </motion.div>
        ))}
      </div>

      {selectedEntry && (
        <div className="glass card-pad mt-6">
          <div className="mb-3 flex items-center justify-between">
            <div className="card-title">Full analysis — {selectedEntry.question}</div>
            <button className="btn btn-ghost btn-sm" onClick={() => setSelected(null)}>Close</button>
          </div>
          <AnalysisResult result={selectedEntry.result} />
        </div>
      )}
    </div>
  );
}