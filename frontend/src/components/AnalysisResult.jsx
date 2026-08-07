import React from "react";
import { AnimatePresence, motion } from "framer-motion";

import { DataTable } from "./DataTable.jsx";
import { PlotlyChart } from "./PlotlyChart.jsx";
import { ConfidenceRing } from "./ConfidenceRing.jsx";
import { stepToPandasSnippet } from "../utils/pandasSnippet.js";

const fadeUp = {
  initial: { opacity: 0, y: 12 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -8 },
};

export function AnalysisResult({ result }) {
  if (!result) return null;
  const { plan, validation, answer, charts, tables, insight, recommendation } = result;
  const structured = result.structured || {};

  return (
    <motion.div
      initial="initial"
      animate="animate"
      className="flex flex-col gap-5"
    >
      {/* Question */}
      <motion.div variants={fadeUp} transition={{ duration: 0.3 }} className="glass card-pad">
        <div className="card-title">Question</div>
        <div className="mt-1 text-base font-semibold text-slate-900 dark:text-white">{result.question}</div>
        <div className="mt-3 flex flex-wrap gap-2">
          <span className="chip chip-accent">intent: {plan.intent}</span>
          <span className="chip">
            {plan.tools.length} tools · {result.execution_time_ms} ms
          </span>
          <span className="chip">mode: {result.llm_mode}</span>
          {validation.corrections?.length > 0 && (
            <span className="chip chip-warning">
              {validation.corrections.length} column correction(s) applied
            </span>
          )}
        </div>
      </motion.div>

      {/* Answer hero */}
      {answer?.label && (
        <motion.div variants={fadeUp} className="glass card-pad">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="min-w-[240px] flex-1">
              <div className="text-[11px] font-bold uppercase tracking-wider text-slate-400">Answer</div>
              <div className="mt-1 flex flex-wrap items-baseline gap-3">
                <span className="text-2xl font-extrabold text-slate-900 dark:text-white">{answer.label}</span>
                <span className="rounded-lg bg-brand-600 px-2.5 py-1 text-base font-bold text-white">{answer.value}</span>
              </div>
              {answer.detail && (
                <div className="mt-1 text-sm text-slate-500 dark:text-slate-400">{answer.detail}</div>
              )}
              {answer.pairs?.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-2">
                  {answer.pairs.map((p, i) => (
                    <span key={i} className="chip">
                      {p.k}: <b>{String(p.v)}</b>
                    </span>
                  ))}
                </div>
              )}
            </div>
            <ConfidenceRing value={result.confidence} />
          </div>
        </motion.div>
      )}

      {/* Executive summary */}
      {structured.executive_summary && (
        <motion.div variants={fadeUp} className="glass card-pad">
          <div className="card-title">Executive Summary</div>
          <p className="mt-2 text-sm leading-relaxed text-slate-700 dark:text-slate-300">
            {structured.executive_summary}
          </p>
        </motion.div>
      )}

      {/* Key findings / recommendations / risks / opportunities */}
      {(structured.key_findings?.length ||
        structured.recommendations?.length ||
        structured.risks?.length ||
        structured.opportunities?.length) && (
        <motion.div variants={fadeUp} className="grid gap-5 sm:grid-cols-2">
          <StructuredBlock title="Key Findings" icon="🔎" items={structured.key_findings} tone="accent" />
          <StructuredBlock title="Recommendations" icon="✅" items={structured.recommendations} tone="success" />
          <StructuredBlock title="Risks" icon="⚠️" items={structured.risks} tone="danger" />
          <StructuredBlock title="Opportunities" icon="🚀" items={structured.opportunities} tone="warning" />
        </motion.div>
      )}

      {/* Execution plan */}
      <motion.div variants={fadeUp} className="glass card-pad">
        <div className="card-title">Execution Plan</div>
        <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">
          {plan.reasoning || plan.intent}
        </div>
        <div className="mt-4 space-y-1">
          {plan.steps.map((s) => (
            <div key={s.step} className="flex gap-3">
              <div className="flex flex-col items-center">
                <div
                  className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-bold ${
                    s.status === "completed"
                      ? "bg-emerald-500/15 text-emerald-500"
                      : s.status === "failed"
                        ? "bg-rose-500/15 text-rose-500"
                        : "bg-brand-500/15 text-brand-500"
                  }`}
                >
                  {s.status === "completed" ? "✓" : s.status === "failed" ? "✕" : s.step}
                </div>
                {s.step < plan.steps.length && <div className="w-px flex-1 bg-slate-200 dark:bg-slate-800" />}
              </div>
              <div className="pb-4">
                <div className="text-sm font-semibold text-slate-800 dark:text-slate-200">
                  <span className="mono text-brand-500 dark:text-brand-400">{s.action}</span>
                  {" — "}
                  {s.description}
                </div>
                {Object.keys(s.params || {}).length > 0 && (
                  <div className="mono mt-1 text-xs text-slate-400">{JSON.stringify(s.params)}</div>
                )}
                {s.note && <div className="mt-1 text-xs text-amber-500">⚠ {s.note}</div>}
                <details className="mt-1.5">
                  <summary className="cursor-pointer text-[11px] text-slate-400 hover:text-brand-500">
                    Show generated Python / Pandas
                  </summary>
                  <pre className="mono mt-2 overflow-x-auto rounded-xl border border-slate-200 bg-slate-900 p-3 text-xs leading-relaxed text-brand-300 dark:border-slate-800">
                    {stepToPandasSnippet(s)}
                  </pre>
                </details>
              </div>
            </div>
          ))}
        </div>
      </motion.div>

      {/* Validation */}
      {validation.issues?.length > 0 && (
        <motion.div variants={fadeUp} className="glass card-pad">
          <div className="card-title">Validation Report</div>
          {validation.issues.map((issue, i) => (
            <div key={i} className="border-b border-slate-200 py-2 last:border-0 dark:border-slate-800">
              <span className={`chip ${severityTone(issue.severity)}`}>{issue.severity}</span>{" "}
              <span className="text-sm">
                <b className="mono text-slate-500 dark:text-slate-400">{issue.code}</b> — {issue.message}
              </span>
              {issue.suggested_fix && (
                <div className="mt-1.5 text-xs text-slate-400">fix: {issue.suggested_fix}</div>
              )}
            </div>
          ))}
        </motion.div>
      )}

      {/* Tables */}
      {tables?.length > 0 && (
        <motion.div variants={fadeUp} className="glass card-pad">
          <div className="card-title">Supporting Tables</div>
          {tables.map((t, i) => (
            <div key={i} className="mb-5 last:mb-0">
              <div className="mb-2 flex items-center justify-between">
                <span className="chip chip-accent mono">{t.tool}</span>
                <span className="text-xs text-slate-400">{t.description}</span>
              </div>
              <DataTable table={t.table} />
            </div>
          ))}
        </motion.div>
      )}

      {/* Charts */}
      {charts?.length > 0 && (
        <div className="grid gap-5 sm:grid-cols-2">
          {charts.map((c, i) => (
            <motion.div variants={fadeUp} className="glass card-pad" key={i}>
              <div className="card-title">Chart · {c.chart_type}</div>
              <div className="mt-1 text-xs text-slate-400">💭 {c.rationale}</div>
              <PlotlyChart figure={c.plotly_json} height={380} />
            </motion.div>
          ))}
        </div>
      )}

      {/* Insight */}
      <motion.div variants={fadeUp} className="glass card-pad">
        <div className="card-title">Business Insight</div>
        {result.text && <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">{result.text}</p>}
        {insight && <p className="mt-2 text-sm leading-relaxed text-slate-800 dark:text-slate-200">{insight}</p>}
        {recommendation && (
          <div className="mt-3">
            <span className="chip chip-success">Recommendation</span>
            <p className="mt-2 text-sm leading-relaxed text-slate-600 dark:text-slate-300">
              {recommendation}
            </p>
          </div>
        )}
        {result.follow_ups?.length > 0 && (
          <div className="mt-4">
            <div className="mb-2 text-[13px] font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
              Follow-ups
            </div>
            <div className="flex flex-wrap gap-2">
              {result.follow_ups.map((f, i) => (
                <span key={i} className="chip chip-accent" title={f.reason}>
                  {f.question}
                </span>
              ))}
            </div>
          </div>
        )}
      </motion.div>
    </motion.div>
  );
}

function StructuredBlock({ title, icon, items, tone }) {
  if (!items || items.length === 0) return null;
  const toneMap = {
    accent: "text-brand-600 dark:text-brand-400",
    success: "text-emerald-600 dark:text-emerald-400",
    danger: "text-rose-600 dark:text-rose-400",
    warning: "text-amber-600 dark:text-amber-400",
  };
  return (
    <div className={`glass card-pad ${tone === "accent" ? "border-brand-200 dark:border-brand-500/30" : ""}`}>
      <div className={`card-title ${toneMap[tone]}`}>
        {icon} {title}
      </div>
      <ul className="mt-2 space-y-1.5">
        {items.map((item, i) => (
          <li key={i} className="text-sm leading-relaxed text-slate-700 dark:text-slate-300">
            • {item}
          </li>
        ))}
      </ul>
    </div>
  );
}

function severityTone(severity) {
  return severity === "error"
    ? "chip-danger"
    : severity === "warning"
      ? "chip-warning"
      : "chip-accent";
}