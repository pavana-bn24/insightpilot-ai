import React from "react";

import { useApp } from "../context/AppContext.jsx";
import { useLocalStorage } from "../hooks/useLocalStorage.js";

export default function SettingsPage() {
  const { health, history } = useApp();
  const [apiBase, setApiBase] = useLocalStorage("insightpilot.api_base", "");
  const [saved, setSaved] = React.useState(false);

  const save = () => {
    setSaved(true);
    setTimeout(() => setSaved(false), 1500);
  };

  return (
    <div className="mx-auto max-w-5xl">
      <header className="mb-6">
        <h1 className="page-title">Settings</h1>
        <p className="page-sub">Runtime configuration and agent behaviour.</p>
      </header>

      <div className="grid gap-5 lg:grid-cols-2">
        <div className="glass card-pad">
          <div className="card-title">Backend connection</div>
          <label className="mt-3 block text-xs text-slate-400">API base URL</label>
          <input
            className="input mt-1"
            value={apiBase}
            onChange={(e) => setApiBase(e.target.value)}
            placeholder="http://localhost:8000 (leave empty for dev proxy)"
          />
          <div className="mt-3 flex items-center gap-2">
            <button className="btn btn-primary" onClick={save}>Save</button>
            {saved && <span className="chip chip-success">Saved ✓</span>}
          </div>
          <div className="mt-5">
            <div className="card-title mb-2">Backend health</div>
            <div className="flex flex-wrap gap-2">
              <span className="chip chip-success">status: {health?.status || "unknown"}</span>
              <span className="chip">provider: {health?.provider || "gemini"}</span>
              <span className="chip">mode: {health?.llm_mode || "deterministic"}</span>
              <span className="chip">datasets: {health?.datasets_loaded ?? 0}</span>
              <span className="chip">analyses: {history.length}</span>
            </div>
          </div>
        </div>

        <div className="glass card-pad">
          <div className="card-title">LLM configuration</div>
          <p className="mt-2 text-xs leading-relaxed text-slate-500 dark:text-slate-400">
            InsightPilot uses the LLM <b>only</b> for planning, explaining and phrasing insights.
            All numbers are always computed by Pandas. The provider is chosen by the{" "}
            <code className="mono">LLM_PROVIDER</code> env var (<b>gemini</b> default, or{" "}
            <code className="mono">openai</code>/<code className="mono">groq</code>/<code className="mono">none</code>).
          </p>
          <pre className="mono mt-3 overflow-x-auto rounded-xl border border-slate-200 bg-slate-900 p-4 text-xs leading-relaxed text-brand-300 dark:border-slate-800">
{`# backend/.env
LLM_PROVIDER=gemini          # gemini | openai | groq | none
GEMINI_API_KEY=...
GEMINI_MODEL=gemini-2.0-flash

# OpenAI / Groq (OpenAI-compatible)
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini`}
          </pre>
          <div className="mt-3 flex flex-wrap gap-2">
            <span className={`chip ${health?.llm_available ? "chip-success" : "chip"}`}>
              LLM client: {health?.llm_available ? health.provider : "offline (deterministic mode)"}
            </span>
          </div>
          <p className="mt-4 text-xs leading-relaxed text-slate-400">
            Without a key the agent runs fully offline with rule-based planning and
            template-generated insights — great for demos and testing.
          </p>
        </div>

        <div className="glass card-pad">
          <div className="card-title">Agent architecture</div>
          <p className="mt-2 text-xs leading-relaxed text-slate-500 dark:text-slate-400">
            Every question goes through six specialised agents:
          </p>
          <ol className="mt-2 list-decimal space-y-1 pl-5 text-xs leading-relaxed text-slate-500 dark:text-slate-400">
            <li><b>Intent &amp; Planning</b> — understands the question, builds an execution plan (with clarification).</li>
            <li><b>Dataset Intelligence</b> — profiles shape, types, missing values, metrics, outliers, quality.</li>
            <li><b>Analysis</b> — executes Pandas tools only (no LLM arithmetic).</li>
            <li><b>Validation</b> — checks results, repairs columns, flags impossible calcs.</li>
            <li><b>Visualization</b> — auto-selects and renders Plotly charts.</li>
            <li><b>Insight</b> — writes explainable, executive business answers.</li>
          </ol>
        </div>

        <div className="glass card-pad">
          <div className="card-title">Data &amp; privacy</div>
          <p className="mt-2 text-xs leading-relaxed text-slate-500 dark:text-slate-400">
            Uploaded datasets live in <code className="mono">backend/data/uploads</code> and are
            stored in memory for the life of the backend process. History is capped at 200
            analyses. Nothing is sent to any third party unless you configure an LLM key —
            and even then only planning prompts and computed facts are sent, never raw data.
          </p>
        </div>
      </div>
    </div>
  );
}