import React, { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";

import { AnalysisResult } from "../components/AnalysisResult.jsx";
import { useApp } from "../context/AppContext.jsx";
import { useAnalysis } from "../hooks/useAnalysis.js";
import { api } from "../services/api.js";
import { exportJSON, exportReport } from "../services/exportUtils.js";

const SUGGESTIONS = [
  "Which region generated the highest revenue?",
  "Show monthly sales trend.",
  "Which product category performed best?",
  "Compare East and West regions by profit.",
  "Calculate profit margin.",
  "Which month had the biggest growth?",
  "What is the correlation between discount and profit?",
  "What is the average revenue per region?",
];

export default function AIAnalyst() {
  const {
    datasets,
    activeDatasetId,
    activeProfile,
    selectDataset,
    refreshHistory,
    suggestions,
    health,
  } = useApp();
  const { result, loading, error, clarification, analyze, clear } = useAnalysis();
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState([]);
  const navigate = useNavigate();
  const scrollRef = useRef(null);

  const displaySuggestions = suggestions.length ? suggestions : SUGGESTIONS;

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, loading, result, clarification]);

  const run = async (q, hints) => {
    if (!q || !q.trim()) return;
    if (!activeDatasetId) {
      navigate("/upload");
      return;
    }
    setMessages((m) => [...m, { role: "user", content: q }]);
    const res = await analyze(activeDatasetId, q.trim(), hints);
    if (res) {
      setMessages((m) => [...m, { role: "assistant", content: q, result: res }]);
      refreshHistory();
    } else if (!clarification) {
      // analyze returned null with no clarification -> error handled below
    }
  };

  const resolveClarification = (option) => {
    if (!clarification) return;
    const hints = option.value || {};
    run(clarification.question, hints);
  };

  const onSubmit = (e) => {
    e?.preventDefault();
    const q = question;
    setQuestion("");
    run(q);
  };

  return (
    <div className="mx-auto max-w-5xl">
      <header className="mb-6">
        <h1 className="page-title">AI Analyst</h1>
        <p className="page-sub">
          Ask in plain English. The agent plans, computes with Pandas, validates, charts and explains.
        </p>
      </header>

      {health && !health.llm_available && <NoKeyBanner provider={health.provider} />}

      {!activeProfile && datasets.length > 0 && (
        <div className="glass card-pad mb-5">
          <div className="card-title">Select a dataset to begin</div>
          <div className="mt-3 flex flex-wrap gap-2">
            {datasets.map((d) => (
              <button key={d.id} className="btn btn-ghost" onClick={() => selectDataset(d.id)}>
                {d.filename} {d.sample ? "(sample)" : `· ${d.rows?.toLocaleString() ?? "?"} rows`}
              </button>
            ))}
          </div>
        </div>
      )}

      {activeProfile && (
        <div className="mb-5 grid grid-cols-2 gap-4 sm:grid-cols-4">
          <ProfileStat label="Dataset" value={activeProfile.filename} />
          <ProfileStat label="Rows" value={activeProfile.rows.toLocaleString()} />
          <ProfileStat label="Metrics" value={activeProfile.possible_metrics.length} />
          <ProfileStat
            label="Dates"
            value={activeProfile.date_columns.length ? "ready" : "none"}
            tone={activeProfile.date_columns.length ? "success" : "warning"}
          />
        </div>
      )}

      {/* Conversation thread */}
      <div
        ref={scrollRef}
        className="glass mb-5 max-h-[60vh] space-y-4 overflow-y-auto p-5"
      >
        {messages.length === 0 && !loading && (
          <div className="py-8 text-center">
            <div className="text-4xl">🧠</div>
            <div className="mt-3 text-sm font-bold text-slate-700 dark:text-slate-300">
              Start a conversation
            </div>
            <p className="mt-1 text-xs text-slate-400">
              Ask a business question and the agent will answer with charts, tables and insights.
            </p>
          </div>
        )}

        <AnimatePresence>
          {messages.map((m, i) => (
            <Message key={i} msg={m} />
          ))}
        </AnimatePresence>

        {loading && <LoadingSkeleton />}

        {/* Clarification prompt */}
        <AnimatePresence>
          {clarification && !loading && (
            <motion.div
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              className="rounded-2xl border border-amber-300/60 bg-amber-50/80 p-4 dark:border-amber-500/30 dark:bg-amber-500/10"
            >
              <div className="text-sm font-bold text-amber-700 dark:text-amber-300">
                🤔 {clarification.message}
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                {clarification.options.map((opt, i) => (
                  <button
                    key={i}
                    onClick={() => resolveClarification(opt)}
                    className="btn btn-ghost"
                    title={opt.description}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Input */}
      <form className="glass card-pad" onSubmit={onSubmit}>
        <div className="card-title mb-2">Ask a question</div>
        <textarea
          className="textarea"
          rows={2}
          placeholder={
            activeProfile
              ? 'e.g. "Which region generated the highest revenue?" or "Show monthly sales trend."'
              : "Upload or select a dataset first…"
          }
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) onSubmit(e);
          }}
        />
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <button
            className="btn btn-primary"
            type="submit"
            disabled={loading || !activeProfile || !question.trim()}
          >
            {loading ? "Running the agent pipeline…" : "⚡ Analyze with the agent"}
          </button>
          <span className="text-xs text-slate-400">Ctrl+Enter to run</span>
          {result && (
            <>
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={() => exportReport(result, "insightpilot-report.md")}
              >
                ⬇ Report (.md)
              </button>
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={() => exportJSON(result, "insightpilot-result.json")}
              >
                ⬇ JSON
              </button>
            </>
          )}
        </div>
        {!activeProfile && (
          <div className="mt-2 text-xs text-slate-400">
            No dataset loaded.{" "}
            <span
              className="cursor-pointer font-semibold text-brand-500"
              onClick={() => navigate("/upload")}
            >
              Upload one
            </span>{" "}
            or pick a sample above.
          </div>
        )}
        {activeProfile && (
          <div className="mt-3 flex flex-wrap gap-2">
            {displaySuggestions.slice(0, 6).map((q) => (
              <button
                key={q}
                type="button"
                onClick={() => run(q)}
                className="chip chip-accent cursor-pointer transition-colors hover:bg-brand-100 dark:hover:bg-brand-500/20"
              >
                {q}
              </button>
            ))}
          </div>
        )}
      </form>

      {error && (
        <div className="glass card-pad mt-4 border-rose-300/60">
          <div className="text-sm font-bold text-rose-500">⚠ {error}</div>
        </div>
      )}
    </div>
  );
}

function Message({ msg }) {
  if (msg.role === "user") {
    return (
      <motion.div
        initial={{ opacity: 0, x: 20 }}
        animate={{ opacity: 1, x: 0 }}
        className="flex justify-end"
      >
        <div className="max-w-[80%] rounded-2xl rounded-br-sm bg-brand-600 px-4 py-2.5 text-sm font-medium text-white shadow-glow">
          {msg.content}
        </div>
      </motion.div>
    );
  }
  return (
    <motion.div
      initial={{ opacity: 0, x: -20 }}
      animate={{ opacity: 1, x: 0 }}
      className="flex justify-start"
    >
      <div className="w-full max-w-[92%]">
        <div className="mb-2 text-xs font-bold uppercase tracking-wider text-brand-500">
          🧠 InsightPilot
        </div>
        {msg.result ? <AnalysisResult result={msg.result} /> : <div className="text-sm">{msg.content}</div>}
      </div>
    </motion.div>
  );
}

function LoadingSkeleton() {
  return (
    <div className="flex justify-start">
      <div className="w-full max-w-[92%] space-y-3">
        <div className="flex items-center gap-2 text-sm text-slate-400">
          <span className="h-2 w-2 animate-ping rounded-full bg-brand-500" />
          Thinking → Planning → Acting with Pandas → Validating → Explaining…
        </div>
        <div className="skeleton h-4 w-1/3" />
        <div className="skeleton h-4 w-1/2" />
        <div className="skeleton h-32 w-full" />
        <div className="skeleton h-4 w-2/3" />
      </div>
    </div>
  );
}

function ProfileStat({ label, value, tone }) {
  const toneColor =
    tone === "success"
      ? "text-emerald-500"
      : tone === "warning"
        ? "text-amber-500"
        : "text-slate-900 dark:text-white";
  return (
    <div className="glass card-pad">
      <div className="text-[11px] font-bold uppercase tracking-wider text-slate-400">{label}</div>
      <div className={`mt-1 truncate text-base font-extrabold ${toneColor}`}>{value}</div>
    </div>
  );
}

function NoKeyBanner({ provider }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: -10 }}
      animate={{ opacity: 1, y: 0 }}
      className="mb-5 flex flex-wrap items-center gap-3 rounded-2xl border border-amber-300/60 bg-amber-50/80 px-4 py-3 dark:border-amber-500/30 dark:bg-amber-500/10"
    >
      <span className="text-lg">🔑</span>
      <div className="min-w-0 flex-1">
        <div className="text-sm font-bold text-amber-700 dark:text-amber-300">
          No {provider} API key configured. AI reasoning features are unavailable.
        </div>
        <div className="text-xs text-amber-600/90 dark:text-amber-400/80">
          Data analysis, charts and dataset exploration still work. Add{" "}
          <code className="mono rounded bg-amber-100/70 px-1 dark:bg-amber-500/15">
            {provider === "gemini" ? "GEMINI_API_KEY" : provider.toUpperCase() + "_API_KEY"}
          </code>{" "}
          to <code className="mono rounded bg-amber-100/70 px-1 dark:bg-amber-500/15">backend/.env</code> to enable
          AI planning and insights.
        </div>
      </div>
    </motion.div>
  );
}
