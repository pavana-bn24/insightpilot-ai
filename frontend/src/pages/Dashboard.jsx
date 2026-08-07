import React from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";

import { StatCard } from "../components/StatCard.jsx";
import { useApp } from "../context/AppContext.jsx";

const SAMPLE_QUESTIONS = [
  "Which region generated the highest revenue?",
  "Show monthly sales trend.",
  "Which product category performed best?",
  "Compare East and West regions by profit.",
  "Calculate profit margin.",
  "Which month had the biggest growth?",
  "What is the correlation between discount and profit?",
  "What is the average revenue per region?",
];

export default function Dashboard() {
  const { datasets, history, health, activeProfile } = useApp();

  const uploaded = datasets.filter((d) => !d.sample);
  const samples = datasets.filter((d) => d.sample);
  const hasDate = activeProfile?.date_columns?.length > 0;

  return (
    <div className="mx-auto max-w-6xl">
      <header className="mb-6">
        <h1 className="page-title">Command Center</h1>
        <p className="page-sub">
          An autonomous BI agent that thinks, plans, acts with Pandas, verifies and explains.
        </p>
      </header>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label="Datasets loaded" value={datasets.length} hint={`${uploaded.length} uploaded · ${samples.length} samples`} />
        <StatCard label="Analyses run" value={history.length} hint="recorded in session history" />
        <StatCard label="Agent mode" value={health?.llm_mode || "—"} hint={health?.llm_available ? "LLM planning + insights" : "deterministic (offline)"} />
        <StatCard label="Active dataset" value={activeProfile ? activeProfile.rows.toLocaleString() : "—"} hint={activeProfile ? `${activeProfile.columns} columns` : "upload or pick a sample"} tone={activeProfile ? "success" : undefined} />
      </div>

      <div className="mt-5 grid gap-5 lg:grid-cols-2">
        <motion.div whileHover={{ y: -2 }} className="glass card-pad">
          <div className="card-title">Start an analysis</div>
          <p className="mt-2 text-sm leading-relaxed text-slate-500 dark:text-slate-400">
            The AI Analyst turns natural-language questions into a structured plan, executes
            real Pandas computations, validates the results, builds charts and writes business
            insights — with full explainability.
          </p>
          <div className="mt-4 flex flex-wrap gap-2">
            <Link to="/analyst" className="btn btn-primary">Open AI Analyst →</Link>
            <Link to="/upload" className="btn btn-ghost">Upload dataset</Link>
            {!activeProfile && (
              <Link to="/explorer" className="btn btn-ghost">Load a sample</Link>
            )}
          </div>
        </motion.div>

        <motion.div whileHover={{ y: -2 }} className="glass card-pad">
          <div className="card-title">Try these questions</div>
          <div className="mt-3 flex flex-wrap gap-2">
            {SAMPLE_QUESTIONS.map((q) => (
              <Link to="/analyst" key={q} className="chip chip-accent cursor-pointer hover:bg-brand-100 dark:hover:bg-brand-500/20">
                {q}
              </Link>
            ))}
          </div>
        </motion.div>
      </div>

      {samples.length > 0 && (
        <div className="glass card-pad mt-5">
          <div className="card-title">Bundled sample datasets</div>
          <div className="mt-3 grid gap-2 sm:grid-cols-2">
            {samples.map((s) => (
              <div key={s.id} className="flex items-center justify-between rounded-xl border border-slate-200 px-4 py-3 dark:border-slate-800">
                <div>
                  <div className="text-sm font-semibold">{s.filename}</div>
                  <div className="text-xs text-slate-400">CSV · sample</div>
                </div>
                <Link to="/explorer" className="btn btn-ghost btn-sm">Explore</Link>
              </div>
            ))}
          </div>
        </div>
      )}

      {!hasDate && activeProfile && (
        <div className="glass card-pad mt-5 border-amber-300/60">
          <div className="text-sm font-bold text-amber-500">⚠ No date column detected</div>
          <p className="mt-1 text-xs leading-relaxed text-slate-500 dark:text-slate-400">
            Trend and growth questions need a date column. If your file has dates, ensure the
            column is formatted as a date (e.g. YYYY-MM-DD) and re-upload.
          </p>
        </div>
      )}
    </div>
  );
}