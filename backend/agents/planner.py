"""Agent 1 - Intent & Planning Agent.

Understands a natural-language question and produces a structured, executable
ExecutionPlan. Works in two modes:

* LLM mode  -- asks the LLM for a plan as JSON (planning/reasoning only, the
               LLM never touches numbers).
* Deterministic mode -- keyword/rule based intent detection with the same
               plan schema, so the agent works fully offline.

Either way the plan only ever references tools from the pandas registry, which
guarantees that all arithmetic happens in Pandas.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

from backend.tools import pandas_tools, similarity
from backend.models.schemas import (
    ClarificationOption,
    DatasetProfile,
    ExecutionPlan,
    PlanStep,
)
from backend.utils.llm.base import LLMProvider
from backend.utils.llm.factory import build_provider, current_provider

# --------------------------------------------------------------------------- #
# Intent rules (deterministic mode)
# --------------------------------------------------------------------------- #
_INTENT_RULES: List[Tuple[str, str]] = [
    # (intent, regex pattern)
    ("trend", r"\b(trend|over\s*time|monthly|quarterly|yearly|weekly|daily|per\s*month|time\s*series|seasonal)\b"),
    ("yoy", r"\b(year[- ]over[- ]year|yoy|yearly comparison|vs last year|compared to last year|annual growth)\b"),
    ("growth", r"\b(growth|grow\w*|%\s*change|percent\s*change|increase|decreased?|fastest\s*growing|biggest\s*growth|improved?|improvement)\b"),
    ("correlation", r"\b(correlat\w*|relationship|related|association)\b"),
    ("margin", r"\b(margin|profitability|profit\s*margin)\b"),
    ("rolling", r"\b(rolling|moving\s*average|smoothed)\b"),
    ("pivot", r"\b(pivot|crosstab|cross\s*tab)\b"),
    ("distribution", r"\b(distribution|histogram|spread|frequency)\b"),
    ("share", r"\b(share|proportion|percentage\s*of|pie)\b"),
    ("compare", r"\b(compare|comparison|versus|\bvs\.?|differenc\w*|against)\b"),
    ("bottom", r"\b(bottom|lowest|worst|minimum|least|smallest|underperforming)\b"),
    ("top", r"\b(top|highest|best|maximum|largest|most|greatest|leading|peak)\b"),
    ("mode", r"\b(mode|most\s*common|most\s*frequent|modal)\b"),
    ("median", r"\b(median)\b"),
    ("average", r"\b(average|\bavg\.?|mean|typical)\b"),
    ("total", r"\b(total|sum|overall|how\s*much|how\s*many)\b"),
    ("summary", r"\b(summary|overview|describe|stats|statistics|profile|shape|info)\b"),
]

# Question phrases that implicitly mean ranking: "which X is Y"
_WHICH = re.compile(r"\bwhich\s+(?P<dim>[\w\s]+?)(\s+(?:has|have|had|generated|produced|earned|showed|posted|did)\s+|\s+is\s+|\s+are\s+)", re.IGNORECASE)
_BY = re.compile(r"\b(grouped?\s*by|by|per|across|for\s+each|breakdown\s+by)\s+(?P<dim>[\w\s]+?)(\s+|\?|$)", re.IGNORECASE)
_COMPARE_X = re.compile(r"\bcompare\s+(?P<x>[\w\s]+?)\s+(?:and|with|vs\.?|to)\s+(?P<y>[\w\s]+)", re.IGNORECASE)

_TIME_WORDS = {
    "month", "months", "year", "years", "quarter", "quarters", "week", "weeks",
    "day", "days", "time", "period", "periods", "date", "dates", "trend",
    "over time", "daily", "weekly", "monthly", "quarterly", "yearly", "annual",
}


def _is_time_word(phrase: str) -> bool:
    return phrase.strip().lower() in _TIME_WORDS


def _detect_intent(question: str) -> str:
    q = question.lower()
    for intent, pattern in _INTENT_RULES:
        if re.search(pattern, q):
            return intent
    return "generic"


class Planner:
    """Builds execution plans from questions."""

    def __init__(self, llm: Optional[LLMProvider] = None) -> None:
        self.llm: LLMProvider = llm or current_provider
        self.mode: str = "deterministic"

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def plan(
        self,
        question: str,
        profile: Optional[DatasetProfile],
        hints: Optional[Dict[str, Any]] = None,
    ) -> ExecutionPlan:
        """Produce an ExecutionPlan for a question against a dataset profile.

        Args:
            question: the user's natural-language question.
            profile: the dataset profile used to resolve columns.
            hints: optional resolution hints from a clarification step, e.g.
                ``{"metric": "Profit", "dim": "Region"}``.
        """
        if self.llm.available:
            plan = self._plan_with_llm(question, profile)
            if plan:
                self.mode = "llm"
                return plan
        plan = self._plan_deterministic(question, profile, hints)
        self.mode = "deterministic"
        return plan

    @property
    def current_mode(self) -> str:
        return self.mode

    # ------------------------------------------------------------------ #
    # LLM planning
    # ------------------------------------------------------------------ #
    def _plan_with_llm(self, question: str, profile: Optional[DatasetProfile]) -> Optional[ExecutionPlan]:
        ctx = self._build_context(profile)
        tool_list = ", ".join(
            f"{n}({', '.join(s.required_params)}) - {s.description}"
            for n, s in pandas_tools.REGISTRY.items()
        )
        prompt = f"""You are the Planning Agent of a business-intelligence AI agent.
You produce a structured execution plan that will be run against a Pandas DataFrame.
You NEVER compute numbers. You only choose which registered tools to call.

Dataset context:
{ctx}

Available tools (name(params) - description):
{tool_list}

Question: "{question}"

Return JSON ONLY with this shape:
{{
  "intent": "short intent label",
  "reasoning": "1-2 sentence justification",
  "steps": [
    {{"action": "tool_name", "description": "what this does", "params": {{...tool params...}}}}
  ]
}}

Rules:
- Use EXACT tool names from the list.
- Pick metric/dimension/date columns that actually exist in the dataset.
- Prefer dimension columns (regions, categories) for "which X"/"by X" questions.
- For trend/growth questions use the detected date column.
- Keep 1-5 steps. First step may be "filter" if the question implies a time window.
"""
        data = self.llm.chat_json([{"role": "user", "content": prompt}])
        if not data:
            return None
        try:
            steps = []
            for i, s in enumerate(data.get("steps", []), start=1):
                action = str(s.get("action", "")).strip()
                if action not in pandas_tools.REGISTRY:
                    continue
                params = self._sanitize_params(action, s.get("params", {}), profile)
                steps.append(
                    PlanStep(
                        step=i,
                        action=action,
                        description=str(s.get("description", action)),
                        params=params,
                    )
                )
            if not steps:
                return None
            return ExecutionPlan(
                intent=str(data.get("intent", "analysis")),
                question=question,
                steps=steps,
                tools=sorted({s.action for s in steps}),
                reasoning=str(data.get("reasoning", "")),
            )
        except Exception:
            return None

    def _sanitize_params(
        self, action: str, params: Dict[str, Any], profile: Optional[DatasetProfile]
    ) -> Dict[str, Any]:
        """Normalise params into valid columns from the actual dataset."""
        known = set()
        if profile:
            known = set(p.name for p in profile.column_profiles)
        clean: Dict[str, Any] = {}
        for k, v in params.items():
            if k in ("column", "x", "y", "group_by", "time_col", "value_col",
                     "revenue_col", "cost_col", "index", "columns", "values",
                     "metric", "group_col"):
                if isinstance(v, str) and profile:
                    resolved = similarity.closest_column(v, list(known))
                    if resolved:
                        clean[k] = resolved
                        continue
                    clean[k] = v
                    continue
            clean[k] = v
        return clean

    # ------------------------------------------------------------------ #
    # Deterministic planning
    # ------------------------------------------------------------------ #
    def _plan_deterministic(
        self,
        question: str,
        profile: Optional[DatasetProfile],
        hints: Optional[Dict[str, Any]] = None,
    ) -> ExecutionPlan:
        ctx = _QuestionContext(question, profile, hints or {})
        intent = _detect_intent(question)

        # Clarification: ask the user instead of guessing.
        if ctx.needs_clarification(intent):
            return ctx.build_clarification_plan(question)

        # --- special intents ----------------------------------------- #
        if intent == "correlation":
            return self._plan_correlation(ctx)
        if intent == "margin":
            return self._plan_margin(ctx)
        if intent == "rolling":
            return self._plan_rolling(ctx)
        if intent == "pivot":
            return self._plan_pivot(ctx)
        if intent == "summary":
            return self._plan_summary(ctx)

        builder = {
            "trend": self._plan_trend,
            "yoy": self._plan_yoy,
            "growth": self._plan_growth,
            "top": self._plan_top,
            "bottom": self._plan_bottom,
            "compare": self._plan_compare,
            "share": self._plan_share,
            "distribution": self._plan_distribution,
            "average": self._plan_average,
            "median": self._plan_median,
            "mode": self._plan_mode,
            "total": self._plan_total,
        }
        if intent in builder:
            return builder[intent](ctx)

        # Generic fallback: explore
        return self._plan_generic(ctx)

    # ------------------------------------------------------------------ #
    # Plan builders
    # ------------------------------------------------------------------ #
    def _plan_trend(self, ctx: "_QuestionContext") -> ExecutionPlan:
        steps: List[PlanStep] = []
        ctx.append_filters(steps)
        time_col = ctx.time_col
        value_col = ctx.metric_col
        group_col = ctx.dim_col
        period = ctx.detect_period()

        if time_col and value_col:
            steps.append(_mk(steps, "time_series",
                             "Resample the metric over time",
                             {"time_col": time_col, "value_col": value_col,
                              "period": period, "group_col": group_col}))
            steps.append(_mk(steps, "insights",
                             "Compute summary statistics of the metric",
                             {"metric_col": value_col}))
        else:
            steps.extend(self._fallback_aggregate_steps(ctx))
        return ExecutionPlan(intent="trend", question=ctx.question, steps=steps,
                             tools=sorted({s.action for s in steps}),
                             reasoning="Question asks about a metric over time, so we resample "
                                       "the metric by period and summarize it.")

    def _plan_growth(self, ctx: "_QuestionContext") -> ExecutionPlan:
        steps: List[PlanStep] = []
        ctx.append_filters(steps)
        if ctx.time_col and ctx.metric_col:
            steps.append(_mk(steps, "time_series",
                             "Aggregate metric by period first",
                             {"time_col": ctx.time_col, "value_col": ctx.metric_col,
                              "period": ctx.detect_period(), "group_col": ctx.dim_col}))
            steps.append(_mk(steps, "growth",
                             "Compute period-over-period growth percentage",
                             {"time_col": ctx.time_col, "value_col": ctx.metric_col,
                              "period": ctx.detect_period(), "group_col": ctx.dim_col}))
            steps.append(_mk(steps, "sort",
                             "Rank periods/groups by growth",
                             {"column": "growth_%", "ascending": False}))
        else:
            steps.extend(self._fallback_aggregate_steps(ctx))
        return ExecutionPlan(intent="growth", question=ctx.question, steps=steps,
                             tools=sorted({s.action for s in steps}),
                             reasoning="Question asks about growth, so we compute percentage "
                                       "change between consecutive periods from the pandas output.")

    def _plan_top(self, ctx: "_QuestionContext") -> ExecutionPlan:
        steps: List[PlanStep] = []
        ctx.append_filters(steps)
        n = ctx.detect_n(default=5)
        agg = ctx.detect_aggregate()
        if ctx.dim_col and ctx.metric_col:
            steps.append(_mk(steps, "group_agg",
                             f"Group by {ctx.dim_col} and {agg} the metric",
                             {"group_by": ctx.dim_col, "aggregate": agg, "metric": ctx.metric_col}))
            top_col = f"{ctx.metric_col}_{agg}"
            steps.append(_mk(steps, "top_n",
                             f"Take top {n} groups", {"column": top_col, "n": n}))
            steps.append(_mk(steps, "sort",
                             "Sort descending", {"column": top_col, "ascending": False}))
        elif ctx.metric_col:
            steps.append(_mk(steps, "top_n",
                             f"Top {n} rows by metric",
                             {"column": ctx.metric_col, "n": n}))
            steps.append(_mk(steps, "sort",
                             "Sort descending", {"column": ctx.metric_col, "ascending": False}))
        else:
            steps.extend(self._fallback_aggregate_steps(ctx))
        return ExecutionPlan(intent="generic", question=ctx.question, steps=steps,
                             tools=sorted({s.action for s in steps}),
                             reasoning="Question asks for top performers, so we aggregate by "
                                       "dimension and rank descending.")

    def _plan_bottom(self, ctx: "_QuestionContext") -> ExecutionPlan:
        steps: List[PlanStep] = []
        ctx.append_filters(steps)
        n = ctx.detect_n(default=5)
        agg = ctx.detect_aggregate()
        if ctx.dim_col and ctx.metric_col:
            steps.append(_mk(steps, "group_agg",
                             f"Group by {ctx.dim_col} and {agg} the metric",
                             {"group_by": ctx.dim_col, "aggregate": agg, "metric": ctx.metric_col}))
            top_col = f"{ctx.metric_col}_{agg}"
            steps.append(_mk(steps, "bottom_n",
                             f"Take bottom {n} groups", {"column": top_col, "n": n}))
            steps.append(_mk(steps, "sort",
                             "Sort ascending", {"column": top_col, "ascending": True}))
        else:
            steps.extend(self._fallback_aggregate_steps(ctx))
        return ExecutionPlan(intent="bottom", question=ctx.question, steps=steps,
                             tools=sorted({s.action for s in steps}),
                             reasoning="Question asks for underperformers, so we aggregate by "
                                       "dimension and rank ascending.")

    def _plan_compare(self, ctx: "_QuestionContext") -> ExecutionPlan:
        steps: List[PlanStep] = []
        ctx.append_filters(steps)
        if ctx.dim_col and ctx.metric_col:
            steps.append(_mk(steps, "compare",
                             "Compare the metric across groups",
                             {"group_by": ctx.dim_col, "metric": ctx.metric_col,
                              "aggregate": ctx.detect_aggregate()}))
            steps.append(_mk(steps, "sort",
                             "Rank groups by metric",
                             {"column": f"{ctx.metric_col}_{ctx.detect_aggregate()}", "ascending": False}))
        elif ctx.metric_col:
            steps.extend(self._fallback_aggregate_steps(ctx))
        else:
            steps.extend(self._fallback_aggregate_steps(ctx))
        return ExecutionPlan(intent="compare", question=ctx.question, steps=steps,
                             tools=sorted({s.action for s in steps}),
                             reasoning="Question asks to compare groups, so we aggregate the "
                                       "metric per dimension and rank.")

    def _plan_share(self, ctx: "_QuestionContext") -> ExecutionPlan:
        steps: List[PlanStep] = []
        ctx.append_filters(steps)
        if ctx.dim_col and ctx.metric_col:
            steps.append(_mk(steps, "group_agg",
                             "Aggregate metric by dimension for share analysis",
                             {"group_by": ctx.dim_col, "aggregate": "sum", "metric": ctx.metric_col}))
        else:
            steps.extend(self._fallback_aggregate_steps(ctx))
        return ExecutionPlan(intent="share", question=ctx.question, steps=steps,
                             tools=sorted({s.action for s in steps}),
                             reasoning="Question asks about share/proportion, so we aggregate the "
                                       "metric by dimension and render a pie chart.")

    def _plan_distribution(self, ctx: "_QuestionContext") -> ExecutionPlan:
        steps: List[PlanStep] = []
        ctx.append_filters(steps)
        if ctx.metric_col:
            steps.append(_mk(steps, "describe",
                             "Distribution statistics of the metric",
                             {"column": ctx.metric_col}))
            steps.append(_mk(steps, "insights",
                             "Summary facts about the metric",
                             {"metric_col": ctx.metric_col}))
        elif ctx.dim_col:
            steps.append(_mk(steps, "value_counts",
                             "Frequency distribution of the dimension",
                             {"column": ctx.dim_col, "n": 15}))
        else:
            steps.extend(self._fallback_aggregate_steps(ctx))
        return ExecutionPlan(intent="distribution", question=ctx.question, steps=steps,
                             tools=sorted({s.action for s in steps}),
                             reasoning="Question asks about distribution, so we produce "
                                       "descriptive statistics and frequency counts.")

    def _plan_average(self, ctx: "_QuestionContext") -> ExecutionPlan:
        steps: List[PlanStep] = []
        ctx.append_filters(steps)
        if ctx.dim_col and ctx.metric_col:
            steps.append(_mk(steps, "group_agg",
                             "Average metric per dimension",
                             {"group_by": ctx.dim_col, "aggregate": "mean", "metric": ctx.metric_col}))
        elif ctx.metric_col:
            steps.append(_mk(steps, "insights",
                             "Compute mean/median facts",
                             {"metric_col": ctx.metric_col}))
        else:
            steps.extend(self._fallback_aggregate_steps(ctx))
        return ExecutionPlan(intent="average", question=ctx.question, steps=steps,
                             tools=sorted({s.action for s in steps}),
                             reasoning="Question asks for an average, so we aggregate by mean.")

    def _plan_median(self, ctx: "_QuestionContext") -> ExecutionPlan:
        steps: List[PlanStep] = []
        ctx.append_filters(steps)
        if ctx.dim_col and ctx.metric_col:
            steps.append(_mk(steps, "group_agg",
                             "Median metric per dimension",
                             {"group_by": ctx.dim_col, "aggregate": "median", "metric": ctx.metric_col}))
        elif ctx.metric_col:
            steps.append(_mk(steps, "insights",
                             "Median facts about the metric",
                             {"metric_col": ctx.metric_col}))
        else:
            steps.extend(self._fallback_aggregate_steps(ctx))
        return ExecutionPlan(intent="median", question=ctx.question, steps=steps,
                             tools=sorted({s.action for s in steps}),
                             reasoning="Question asks for a median, so we aggregate by median.")

    def _plan_total(self, ctx: "_QuestionContext") -> ExecutionPlan:
        steps: List[PlanStep] = []
        ctx.append_filters(steps)
        if ctx.dim_col and ctx.metric_col:
            steps.append(_mk(steps, "group_agg",
                             "Total metric per dimension",
                             {"group_by": ctx.dim_col, "aggregate": "sum", "metric": ctx.metric_col}))
            steps.append(_mk(steps, "sort",
                             "Rank by total",
                             {"column": f"{ctx.metric_col}_sum", "ascending": False}))
        elif ctx.metric_col:
            steps.append(_mk(steps, "insights",
                             "Compute totals and summary facts",
                             {"metric_col": ctx.metric_col}))
        else:
            steps.extend(self._fallback_aggregate_steps(ctx))
        return ExecutionPlan(intent="total", question=ctx.question, steps=steps,
                             tools=sorted({s.action for s in steps}),
                             reasoning="Question asks for totals, so we sum the metric per dimension.")

    def _plan_yoy(self, ctx: "_QuestionContext") -> ExecutionPlan:
        """Year-over-year comparison of a metric (optionally by dimension)."""
        steps: List[PlanStep] = []
        ctx.append_filters(steps)
        if ctx.time_col and ctx.metric_col:
            steps.append(_mk(steps, "yoy",
                             "Compute year-over-year comparison",
                             {"time_col": ctx.time_col, "value_col": ctx.metric_col,
                              "group_col": ctx.dim_col}))
            steps.append(_mk(steps, "time_series",
                             "Resample metric yearly for context",
                             {"time_col": ctx.time_col, "value_col": ctx.metric_col,
                              "period": "Y", "group_col": ctx.dim_col}))
        else:
            steps.extend(self._fallback_aggregate_steps(ctx))
        return ExecutionPlan(intent="yoy", question=ctx.question, steps=steps,
                             tools=sorted({s.action for s in steps}),
                             reasoning="Question asks for a year-over-year comparison, so we "
                                       "group by year and compute YoY growth from pandas.")

    def _plan_mode(self, ctx: "_QuestionContext") -> ExecutionPlan:
        steps: List[PlanStep] = []
        ctx.append_filters(steps)
        if ctx.dim_col:
            steps.append(_mk(steps, "value_counts",
                             "Most frequent values of the dimension",
                             {"column": ctx.dim_col, "n": 10}))
        elif ctx.metric_col:
            steps.append(_mk(steps, "mode",
                             "Statistical mode of the metric",
                             {"column": ctx.metric_col}))
        else:
            steps.extend(self._fallback_aggregate_steps(ctx))
        return ExecutionPlan(intent="mode", question=ctx.question, steps=steps,
                             tools=sorted({s.action for s in steps}),
                             reasoning="Question asks for the most common value, so we compute "
                                       "the mode/frequency distribution in pandas.")

    def _plan_correlation(self, ctx: "_QuestionContext") -> ExecutionPlan:
        steps: List[PlanStep] = []
        ctx.append_filters(steps)
        if len(ctx.numeric_cols) >= 2:
            x, y = ctx.extract_two_metrics()
            if not (x and y):
                x = ctx.metric_col
                others = [c for c in ctx.numeric_cols if c != x]
                y = others[0] if others else None
            steps.append(_mk(steps, "correlation",
                             "Compute Pearson correlation",
                             {"x": x, "y": y}))
        else:
            steps.append(_mk(steps, "describe", "Dataset too small for correlation",
                             {"column": ctx.metric_col} if ctx.metric_col else {}))
        return ExecutionPlan(intent="correlation", question=ctx.question, steps=steps,
                             tools=sorted({s.action for s in steps}),
                             reasoning="Question asks about correlation, so we compute the "
                                       "Pearson coefficient from pandas only.")

    def _plan_margin(self, ctx: "_QuestionContext") -> ExecutionPlan:
        steps: List[PlanStep] = []
        ctx.append_filters(steps)
        rev, cost = ctx.find_margin_columns()
        if rev and cost:
            steps.append(_mk(steps, "kpi_margin",
                             "Compute profit and profit margin",
                             {"revenue_col": rev, "cost_col": cost, "group_by": ctx.dim_col}))
        else:
            steps.extend(self._fallback_aggregate_steps(ctx))
        return ExecutionPlan(intent="margin", question=ctx.question, steps=steps,
                             tools=sorted({s.action for s in steps}),
                             reasoning="Question asks about margin, so we compute profit = "
                                       "revenue - cost and margin % from the data.")

    def _plan_rolling(self, ctx: "_QuestionContext") -> ExecutionPlan:
        steps: List[PlanStep] = []
        ctx.append_filters(steps)
        window = ctx.detect_n(default=3)
        if ctx.metric_col:
            steps.append(_mk(steps, "rolling",
                             f"Compute {window}-period rolling average",
                             {"column": ctx.metric_col, "window": window}))
        else:
            steps.extend(self._fallback_aggregate_steps(ctx))
        return ExecutionPlan(intent="rolling", question=ctx.question, steps=steps,
                             tools=sorted({s.action for s in steps}),
                             reasoning="Question asks for a rolling/moving average, so we "
                                       "compute it in pandas.")

    def _plan_pivot(self, ctx: "_QuestionContext") -> ExecutionPlan:
        steps: List[PlanStep] = []
        ctx.append_filters(steps)
        if ctx.dim_col and ctx.metric_col:
            steps.append(_mk(steps, "pivot",
                             "Build a pivot table",
                             {"index": ctx.dim_col, "columns": ctx.pivot_col or ctx.dim_col,
                              "values": ctx.metric_col, "aggfunc": "sum"}))
        else:
            steps.extend(self._fallback_aggregate_steps(ctx))
        return ExecutionPlan(intent="pivot", question=ctx.question, steps=steps,
                             tools=sorted({s.action for s in steps}),
                             reasoning="Question asks for a pivot, so we aggregate metric by "
                                       "the index and column dimensions.")

    def _plan_summary(self, ctx: "_QuestionContext") -> ExecutionPlan:
        steps: List[PlanStep] = []
        steps.append(_mk(steps, "describe", "Descriptive statistics of all numeric columns", {}))
        steps.append(_mk(steps, "head", "Preview first rows of the dataset", {"n": 10}))
        return ExecutionPlan(intent="summary", question=ctx.question, steps=steps,
                             tools=sorted({s.action for s in steps}),
                             reasoning="Question asks for an overview, so we describe the "
                                       "dataset and preview rows.")

    def _plan_generic(self, ctx: "_QuestionContext") -> ExecutionPlan:
        return self._plan_top(ctx)

    def _fallback_aggregate_steps(self, ctx: "_QuestionContext") -> List[PlanStep]:
        """Generic steps used when no metric/dimension is identified."""
        steps: List[PlanStep] = []
        numeric = ctx.numeric_cols or []
        if numeric:
            steps.append(_mk(steps, "insights",
                             "Summary facts about the primary numeric column",
                             {"metric_col": numeric[0]}))
            steps.append(_mk(steps, "describe",
                             "Descriptive statistics",
                             {"column": numeric[0]}))
        else:
            steps.append(_mk(steps, "head", "Preview rows", {"n": 10}))
        return steps

    # ------------------------------------------------------------------ #
    def _build_context(self, profile: Optional[DatasetProfile]) -> str:
        if not profile:
            return "No dataset loaded."
        lines = [
            f"Rows: {profile.rows}, Columns: {profile.columns}",
            f"Numeric columns: {profile.numeric_columns}",
            f"Categorical columns: {profile.categorical_columns}",
            f"Date columns: {profile.date_columns}",
            f"Possible metrics: {profile.possible_metrics}",
        ]
        return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Question context: entity extraction helpers (deterministic mode)
# --------------------------------------------------------------------------- #
class _QuestionContext:
    """Extracts metric/dimension/date/filter entities from a question.

    ``hints`` (from a prior clarification step) take precedence over heuristics:
    ``{"metric": "Profit", "dim": "Region", "time": "Date"}``.
    """

    def __init__(
        self,
        question: str,
        profile: Optional[DatasetProfile],
        hints: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.question = question
        self.profile = profile
        self.hints = hints or {}
        self.columns = [p.name for p in profile.column_profiles] if profile else []
        self.numeric_cols = profile.numeric_columns if profile else []
        self.cat_cols = profile.categorical_columns if profile else []
        self.date_cols = profile.date_columns if profile else []
        self.metrics = profile.possible_metrics if profile else []
        self.time_col = self._pick_time_col()
        self.metric_col = self._pick_metric_col()
        self.dim_col = self._pick_dim_col()
        self.pivot_col = self._pick_pivot_col()

    # -- entity extraction ------------------------------------------- #
    def _mentions(self, name: str) -> bool:
        q = similarity.normalize(self.question)
        tokens = set(similarity.tokenize(self.question))
        name_tokens = set(similarity.tokenize(name))
        if not name_tokens:
            return False
        return name_tokens.issubset(tokens) or similarity.normalize(name) in q

    def _pick_time_col(self) -> Optional[str]:
        hint = self.hints.get("time")
        if hint:
            return similarity.closest_column(hint, self.date_cols) if self.date_cols else None
        if not self.date_cols:
            return None
        for c in self.date_cols:
            if self._mentions(c):
                return c
        return self.date_cols[0]

    def _pick_metric_col(self) -> Optional[str]:
        hint = self.hints.get("metric")
        if hint:
            return similarity.closest_column(hint, self.numeric_cols) or hint
        for m in self.metrics:
            if self._mentions(m):
                return m
        for m in self.numeric_cols:
            if self._mentions(m):
                return m
        return similarity.pick_metric(self.numeric_cols)

    def _pick_dim_col(self) -> Optional[str]:
        """Pick the grouping dimension, or None if the question is time-focused."""
        hint = self.hints.get("dim")
        if hint:
            return similarity.closest_column(hint, self.cat_cols) or (
                hint if hint in self.columns else None
            )
        # "which <dim>" capture
        m = _WHICH.search(self.question)
        if m:
            dim = m.group("dim").strip()
            if _is_time_word(dim):
                return None  # "which month/year/..." -> time axis, not a dimension
            if dim:
                resolved = self._resolve_dim(dim)
                if resolved:
                    return resolved
        # explicit by/per phrases
        m = _BY.search(self.question)
        if m:
            dim = m.group("dim").strip()
            if dim:
                resolved = self._resolve_dim(dim)
                if resolved:
                    return resolved
        # column mentioned directly
        for c in self.cat_cols:
            if self._mentions(c):
                return c
        # Default to the first categorical column, unless the question is
        # time-focused (trend/growth/monthly...), in which case leave it to the
        # time axis rather than forcing an arbitrary breakdown.
        if self._is_time_focused():
            return None
        return self.cat_cols[0] if self.cat_cols else None

    def _is_time_focused(self) -> bool:
        q = self.question.lower()
        return bool(
            re.search(r"\b(trend|over\s*time|monthly|quarterly|yearly|weekly|daily|time\s*series)\b", q)
            or self.time_col is not None and re.search(r"\b(month|year|quarter|week|day)\b", q)
        )

    def _pick_pivot_col(self) -> Optional[str]:
        for c in self.cat_cols:
            if c != self.dim_col and self._mentions(c):
                return c
        if self.cat_cols and len(self.cat_cols) > 1:
            return self.cat_cols[1]
        return None

    def _resolve_dim(self, phrase: str) -> Optional[str]:
        """Resolve a phrase to the best matching column, or None.

        Time-related phrases (month, year, quarter, ...) are never treated as
        grouping dimensions when a date column exists -- they describe the time
        axis of the analysis, not a categorical breakdown.
        """
        phrase_lower = phrase.lower().rstrip("?")
        if _is_time_word(phrase_lower):
            return None
        best, best_score = None, 0.0
        for c in self.columns:
            score = similarity.similarity_score(phrase_lower, c)
            if score > best_score:
                best, best_score = c, score
        if best_score >= 0.35:
            return best
        return None

    def find_margin_columns(self) -> Tuple[Optional[str], Optional[str]]:
        rev = cost = None
        for c in self.numeric_cols:
            nc = similarity.normalize(c)
            if not rev and any(k in nc for k in ("revenue", "sales", "income", "amount", "gmv")):
                rev = c
            if not cost and any(k in nc for k in ("cost", "expense", "expenses", "cogs", "spend")):
                cost = c
        if not rev and len(self.numeric_cols) >= 2:
            rev = self.numeric_cols[0]
            cost = self.numeric_cols[1]
        return rev, cost

    def extract_two_metrics(self) -> Tuple[Optional[str], Optional[str]]:
        """Return the two numeric columns explicitly mentioned in the question."""
        mentioned = [c for c in self.numeric_cols if self._mentions(c)]
        if len(mentioned) >= 2:
            return mentioned[0], mentioned[1]
        return None, None

    # ------------------------------------------------------------------ #
    # Clarification (autonomous ambiguity handling)
    # ------------------------------------------------------------------ #
    def _metric_ambiguous(self) -> bool:
        if self.hints.get("metric"):
            return False
        mentioned = [c for c in self.numeric_cols if self._mentions(c)]
        return not mentioned and len(self.numeric_cols) >= 2

    def _dim_ambiguous(self) -> bool:
        if self.hints.get("dim"):
            return False
        return self.dim_col is None and bool(self.cat_cols)

    def needs_clarification(self, intent: Optional[str] = None) -> bool:
        """True if the question is ambiguous enough to ask the user.

        Fires only for open-ended analytical intents where the planner cannot
        confidently pick a metric or dimension column.
        """
        if intent is None:
            intent = _detect_intent(self.question)
        if intent not in ("top", "bottom", "compare", "total", "share", "average", "median"):
            return False
        return self._metric_ambiguous() or self._dim_ambiguous()

    def build_clarification_plan(self, question: str) -> ExecutionPlan:
        """Build an ExecutionPlan that asks the user to resolve ambiguity."""
        options: List[ClarificationOption] = []

        if self._metric_ambiguous():
            for m in self.numeric_cols:
                options.append(
                    ClarificationOption(
                        label=m,
                        description=f"Analyse the {m} metric",
                        value={"metric": m},
                    )
                )

        if self._dim_ambiguous():
            for d in self.cat_cols[:4]:
                options.append(
                    ClarificationOption(
                        label=d,
                        description=f"Break down the result by {d}",
                        value={"dim": d},
                    )
                )

        message = (
            "Your question could be answered in a few ways. "
            "Please pick the column you meant."
        )
        return ExecutionPlan(
            intent="clarification",
            question=question,
            steps=[],
            tools=[],
            reasoning="The planner detected column ambiguity and is asking the user to resolve it.",
            needs_clarification=True,
            clarification_message=message,
            clarification_options=options,
        )

    # -- filters ------------------------------------------------------- #
    def append_filters(self, steps: List[PlanStep]) -> None:
        window = self.detect_time_window()
        if window and self.time_col:
            params = {"column": self.time_col, "condition": window[0], "value": window[1]}
            steps.append(_mk(steps, "filter",
                             f"Filter to {window[1]}", params))

    def detect_time_window(self) -> Optional[Tuple[str, Any]]:
        q = self.question.lower()
        year = re.search(r"\b(19|20)\d{2}\b", q)
        if year:
            return "gte", f"{year.group(0)}-01-01"
        if "last year" in q or "previous year" in q:
            import datetime as _dt

            y = _dt.date.today().year - 1
            return "between", f"{y}-01-01:{y}-12-31"
        if "this year" in q or "current year" in q:
            import datetime as _dt

            y = _dt.date.today().year
            return "between", f"{y}-01-01:{y}-12-31"
        if "last quarter" in q:
            import datetime as _dt

            q_now = (_dt.date.today().month - 1) // 3
            return "between", f"quarter:{q_now}"
        return None

    def detect_period(self) -> str:
        q = self.question.lower()
        if "daily" in q or "day" in q and "weekday" not in q:
            return "D"
        if "weekly" in q or "week" in q:
            return "W"
        if "quarter" in q or "quarterly" in q:
            return "Q"
        if "year" in q or "yearly" in q or "annual" in q:
            return "Y"
        return "M"

    def detect_n(self, default: int = 5) -> int:
        m = re.search(r"\b(top|bottom|last|first)\s+(\d+)", self.question.lower())
        if m:
            return int(m.group(2))
        m = re.search(r"\b(\d+)\s+(?:top|best|worst|rows|records)\b", self.question.lower())
        if m:
            return int(m.group(1))
        return default

    def detect_aggregate(self) -> str:
        q = self.question.lower()
        if "average" in q or "mean" in q or "avg" in q:
            return "mean"
        if "median" in q:
            return "median"
        if "count" in q or "how many" in q:
            return "count"
        if "maximum" in q or "max" in q:
            return "max"
        if "minimum" in q or "min" in q:
            return "min"
        return "sum"


# --------------------------------------------------------------------------- #
# Step helpers
# --------------------------------------------------------------------------- #
def _mk(steps: List[PlanStep], action: str, description: str, params: Dict[str, Any]) -> PlanStep:
    return PlanStep(step=len(steps) + 1, action=action, description=description, params=params)


planner = Planner()
