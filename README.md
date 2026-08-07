# 🧠 InsightPilot AI

**An Autonomous AI Business Intelligence Agent** that answers natural-language questions over
CSV / Excel datasets using a complete **Think → Plan → Clarify → Act → Verify → Explain** workflow with
planning, tool execution, validation, visualization, and explainable reasoning.

Built as an **AI Research Associate portfolio project** — not a chatbot, but an autonomous
analyst that *plans*, *computes real numbers with Pandas*, *validates*, *charts*, and *explains*
every answer.

---

## ✨ Highlights

| Capability | How it works |
|---|---|
| Load CSV / Excel | `data_loader` auto-detects encodings, dates, column types |
| Understand dataset structure | Dataset Intelligence Agent builds a full **Dataset Profile** (incl. outliers + quality score) |
| Plain-English questions | Intent & Planning Agent maps questions → structured execution plans |
| Ambiguity handling | Planner asks **clarification questions** instead of guessing columns |
| Real computations | **100% Pandas** — the LLM never touches numbers |
| No hallucinated numbers | Validation Agent + computed-only facts feed the Insight Agent |
| Executive insights | Structured `executive_summary / key_findings / recommendations / risks / opportunities` |
| Supporting tables | Every intermediate step rendered as a table |
| Charts | Rule-based chart selection → interactive **Plotly** figures |
| Conversation history | The AI Analyst keeps a full user↔agent thread with full result payloads |
| Explainable AI | Question · Plan · Tools · Pandas code · Result · Insight · Confidence · Follow-ups |
| Premium UI | Tailwind CSS + Framer Motion, dark/light mode, loading skeletons, animated cards |
| Export | CSV / JSON / PNG / Markdown report |

---

## 🏗️ Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                       FRONTEND (React 18 + Vite)                     │
│   Dashboard · Upload · Explorer · AI Analyst · Charts · Insights ·   │
│   History · Settings      (TailwindCSS + Framer Motion, dark/light)  │
└───────────────────────────────┬──────────────────────────────────────┘
                                │  REST (FastAPI)
┌───────────────────────────────▼──────────────────────────────────────┐
│                          BACKEND (FastAPI)                           │
│                                                                      │
│   ┌──────────────────────── AGENT PIPELINE ────────────────────────┐ │
│   │  1. Intent & Planning Agent   → ExecutionPlan (+ clarification)│ │
│   │  2. Dataset Intelligence Agent → DatasetProfile (quality score)│ │
│   │  3. Analysis Agent            → pandas computation (only)      │ │
│   │  4. Validation Agent          → validation + repair + closest  │ │
│   │  5. Visualization Agent       → Plotly chart specs             │ │
│   │  6. Insight Agent             → answer · insight · structured  │ │
│   └─────────────────────────────────────────────────────────────────┘ │
│                                                                      │
│   api/routes.py   models/schemas.py   tools/   utils/llm/            │
│   main.py (app)   (Pydantic models)   pandas_tools · similarity ·    │
│   pipeline.py                         data_loader · chart_tools      │
│   agents/                              llm/base · gemini ·           │
│                                        openai_compat · factory       │
└──────────────────────────────────────────────────────────────────────┘
```

### The six agents

1. **Intent & Planning Agent** — understands the question, decides which registered tools are
   needed, and emits a structured `ExecutionPlan` (LLM-backed planning with a deterministic
   offline fallback). When the question is ambiguous it emits a **clarification request** with
   concrete options (e.g. "which metric did you mean?").
2. **Dataset Intelligence Agent** — automatically profiles rows, columns, dtypes, missing values,
   duplicates, numeric/categorical/date columns, IQR **outliers**, possible business metrics and a
   **data-quality score** (0–100).
3. **Analysis Agent** — the *only* place numbers are computed. Executes registered Pandas tools
   (filter, group, aggregate, correlation, pivot, growth %, YoY, mode, outliers, rolling average,
   top/bottom N, KPIs…).
4. **Validation Agent** — catches missing columns (and suggests the **closest match**), empty
   results, division-by-zero, invalid dates and impossible calculations.
5. **Visualization Agent** — rule-based chart selection (trend → line, comparison → bar,
   distribution → histogram, correlation → scatter, share → pie) rendered as interactive Plotly.
6. **Insight Agent** — turns computed numbers into a headline answer, business insight,
   recommendation, confidence score, suggested follow-up questions and **executive structured
   insights**.

### Golden rule

> **The LLM plans, reasons, explains and phrases. Pandas computes. Nothing else.**

When no LLM key is configured, deterministic rule-based planning + template insights keep the
whole agent fully functional offline.

---

## 🧰 Technology Stack

| Layer | Tech |
|---|---|
| Backend | Python 3.11+, FastAPI, Uvicorn, Pydantic v2 |
| Computation | Pandas, NumPy |
| Charts | Plotly (figure JSON → frontend) |
| Frontend | React 18, Vite, React Router |
| UI | **Tailwind CSS**, **Framer Motion**, dark/light mode |
| Charting in browser | plotly.js (lazy-loaded) |
| LLM (optional) | **Gemini** (default) / OpenAI / Groq via OpenAI-compatible providers |
| Styling | TailwindCSS design system (dark glassmorphism) |

---

## 🚀 Installation

### Prerequisites
- Python 3.11+ and Node.js 18+

### 1. Backend

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate    |    macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Frontend

```bash
cd frontend
npm install
```

---

## 🔑 Environment Variables

Create `backend/.env` from the template:

```bash
cp backend/.env.example backend/.env
```

| Variable | Purpose | Default |
|---|---|---|
| `LLM_PROVIDER` | Provider: `gemini` \| `openai` \| `groq` \| `none` | `gemini` |
| `GEMINI_API_KEY` | Enables Gemini LLM planning/insight phrasing | *(empty)* |
| `GEMINI_MODEL` | Gemini model name | `gemini-2.0-flash` |
| `OPENAI_API_KEY` / `OPENAI_BASE_URL` / `OPENAI_MODEL` | OpenAI (or compatible) provider | `gpt-4o-mini` |
| `GROQ_API_KEY` / `GROQ_BASE_URL` / `GROQ_MODEL` | Groq provider | `llama-3.3-70b-versatile` |
| `HOST` / `PORT` | Server bind address | `0.0.0.0` / `8000` |

> Privacy note: without an LLM key, nothing ever leaves your machine. With a key, only planning
> prompts and already-computed facts are sent — raw datasets are never uploaded.

---

## ▶️ Running the Backend

```bash
cd backend
python -m uvicorn backend.main:app --reload --port 8000
```

API is served at `http://localhost:8000` (docs at `/docs`). Bundled sample datasets are
auto-generated on first use (`backend/data/samples/*.csv`).

## ▶️ Running the Frontend (development)

```bash
cd frontend
npm run dev
```

Open `http://localhost:5173`. The Vite dev server proxies `/api` → `http://localhost:8000`.

### Production single-server mode

```bash
cd frontend && npm run build        # outputs frontend/dist
cd .. && python -m uvicorn backend.main:app --port 8000
```

The backend serves the built React app at `http://localhost:8000`.

---

## 🤖 How the Agent Works

For every question the pipeline runs:

```
Question ──▶ Intent & Planning ──▶ ExecutionPlan (steps → registered tools)
                 │                      │
                 │ (ambiguous?)         ▼
                 │   ──▶ clarification request ──▶ user picks → rerun with hints
                 ▼
         Analysis Agent (Pandas) ◀── each step resolves to a tool fn
                 │
                 ▼
         Validation Agent ──▶ repairs columns / flags impossible calcs
                 │
                 ▼
         Visualization Agent ──▶ Plotly charts (auto chart-type)
                 │
                 ▼
         Insight Agent ──▶ answer · structured insights · recommendation · confidence · follow-ups
```

Every step keeps its own pandas result, so the supporting tables show the *exact* computation
chain. The UI exposes the generated Python/Pandas snippet per step.

---

## ❓ Sample Questions

| Question | Intent detected |
|---|---|
| Which region generated the highest revenue? | `top` |
| Show monthly sales trend. | `trend` |
| Which product category performed best? | `clarification` → `top` (after picking a metric) |
| Compare East and West regions by profit. | `compare` |
| Calculate profit margin. | `margin` |
| Which month had the biggest growth? | `growth` |
| What is the correlation between discount and profit? | `correlation` |
| What is the average revenue per region? | `average` |
| What is the revenue YoY growth? | `yoy` |
| What is the most common region? | `mode` |
| What is the median profit by category? | `median` |
| What is the total cost across all regions? | `total` |
| What is the rolling 3-month average of revenue? | `rolling` |
| What is the distribution of revenue? | `distribution` |

---

## 📊 Sample Outputs

**Question:** Which region generated the highest revenue?

| Answer | Value |
|---|---|
| West | ₹1.2M |

**Execution plan (3 steps, all ✓):**
1. `group_agg` — group by Region, sum Revenue
2. `top_n` — take top 5 groups
3. `sort` — sort descending

**Executive summary:** *West leads with ₹1.2M; the gap to the smallest group is ₹174.5K.*
**Recommendation:** *Investigate what drives success in West and replicate it across other groups.*
**Confidence:** 94% · **Charts:** bar · **Tables:** 3 supporting tables

**Question:** What is the correlation between discount and profit?

> **Answer:** weak correlation, Pearson r = -0.00
> **Insight:** *There is a weak negative linear relationship between Discount and Profit.*

*(Actual computed number from pandas — never fabricated.)*

---

## ⚖️ Tradeoffs

- **In-memory state** keeps the demo simple and dependency-free; restarting the backend resets
  history. (Swap for SQLite/Redis in production.)
- **Deterministic planning** guarantees reproducible, offline answers but is less flexible than
  LLM planning. Enable an API key for richer plan phrasing while arithmetic stays in Pandas.
- **Rule-based chart selection** is predictable (great for explainability) but less adaptive than
  learned chart recommendation.
- **`plotly.js` lazy-load** keeps the initial bundle small at the cost of a small first-chart load
  delay.

---

## 🔮 Future Improvements

- Vector-retrieval over column metadata for smarter column disambiguation.
- Streaming / step-by-step live updates during long analyses.
- Multi-dataset joins and SQL-caching for large files (DuckDB/Parquet backend).
- Richer clarification (date ranges, aggregation choices) driven by the LLM planner.
- Anomaly explanations tied to the outlier detection tool.
- Export to PDF/XLSX dashboards and scheduled report generation.
- Fine-tuned planning prompts with few-shot examples per industry vertical.

---

## 📁 Project Structure

```
backend/
  api/routes.py        # all REST endpoints (analyze, history, conversation, suggestions, …)
  agents/              # six agent implementations
  models/schemas.py    # shared Pydantic models (DatasetProfile, ExecutionPlan, …)
  tools/               # data_loader, pandas_tools, chart_tools, similarity
  utils/llm/           # base.py, gemini.py, openai_compat.py, factory.py (provider abstraction)
  data/                # uploads/ (runtime) + samples/ (bundled demo CSVs)
  main.py              # FastAPI app factory (mounts routes + serves built frontend)
  pipeline.py          # agent orchestration (incl. clarification flow)
  smoke_test.py        # pipeline regression test (9 questions)
  api_test.py          # endpoint smoke test
  excel_test.py        # Excel upload + chart validity test
frontend/
  src/components/      # reusable UI (charts, tables, plan stepper, analysis result, …)
  src/pages/           # Dashboard, Upload, Explorer, Analyst, Charts, Insights, History, Settings
  src/hooks/           # useAnalysis, useLocalStorage
  src/services/        # api client, export utils
  src/context/         # global app state (datasets, theme, suggestions)
  src/styles/          # TailwindCSS design system
  tailwind.config.js   # theme + dark mode config
README.md
```

---

## 🧪 Running the tests

```bash
# On Windows set the console encoding first so ₹ prints correctly:
$env:PYTHONIOENCODING="utf-8"

python backend/smoke_test.py    # pipeline end-to-end (9 questions)
python backend/api_test.py      # FastAPI endpoint smoke test
python backend/excel_test.py    # Excel upload + chart JSON validity
```
