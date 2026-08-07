import React, { useEffect, useState } from "react";
import { motion } from "framer-motion";

import { PlotlyChart } from "../components/PlotlyChart.jsx";
import { api } from "../services/api.js";
import { exportChartPNG } from "../services/exportUtils.js";
import { useApp } from "../context/AppContext.jsx";

export default function ChartsPage() {
  const { refreshHistory } = useApp();
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      const h = await api.history();
      setHistory(h);
      setLoading(false);
    })();
  }, [refreshHistory]);

  const items = [];
  for (const h of history) {
    const charts = h.result?.charts || [];
    charts.forEach((c, i) => {
      items.push({ ...c, question: h.question, historyId: h.id, chartIdx: i });
    });
  }

  return (
    <div className="mx-auto max-w-6xl">
      <header className="mb-6">
        <h1 className="page-title">Charts</h1>
        <p className="page-sub">Interactive Plotly charts generated automatically from each analysis.</p>
      </header>

      {loading && (
        <div className="glass card-pad flex items-center justify-center gap-3">
          <span className="h-4 w-4 animate-spin rounded-full border-2 border-brand-500 border-t-transparent" />
          Loading charts…
        </div>
      )}

      {!loading && items.length === 0 && (
        <div className="glass card-pad text-center">
          <div className="text-4xl">📈</div>
          <div className="mt-2 text-base font-bold text-slate-800 dark:text-slate-200">No charts yet</div>
          <p className="mt-1 text-sm text-slate-400">Run an analysis in the AI Analyst to generate charts.</p>
        </div>
      )}

      <div className="grid gap-5 md:grid-cols-2">
        {items.map((chart, idx) => (
          <motion.div
            key={`${chart.historyId}-${chart.chartIdx}`}
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: idx * 0.03 }}
            className="glass card-pad"
          >
            <div className="flex items-center justify-between">
              <div>
                <span className="chip chip-accent">{chart.chart_type}</span>
                <span className="ml-2 text-xs text-slate-400">{chart.question}</span>
              </div>
              <button
                className="btn btn-ghost btn-sm"
                onClick={() =>
                  exportChartPNG(chart.plotly_json, `chart-${chart.chart_type}-${chart.question.slice(0, 20).replace(/\W+/g, "_")}.png`)
                }
              >
                ⬇ PNG
              </button>
            </div>
            <div className="mt-2 text-xs text-slate-400">💭 {chart.rationale}</div>
            <div className="mt-2">
              <PlotlyChart figure={chart.plotly_json} height={380} />
            </div>
          </motion.div>
        ))}
      </div>
    </div>
  );
}