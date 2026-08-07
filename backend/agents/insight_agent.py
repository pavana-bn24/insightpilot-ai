"""Agent 6 - Insight Agent.

Converts *computed* numbers (produced exclusively by Pandas) into a readable,
business-oriented answer: a headline, supporting facts, business insight,
recommendation, confidence score and suggested follow-ups.

The LLM may be used to phrase the insight, but it only ever receives the
already-computed facts and is instructed to reference them verbatim -- it never
invents values. Without an LLM key a deterministic template engine produces
equivalent output.
"""
from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional

from backend.agents.analysis_agent import AnalysisOutcome
from backend.models.schemas import (
    ExecutionPlan,
    FollowUp,
    QueryResult,
    StructuredInsights,
    ValidationReport,
)
from backend.utils.llm.base import LLMProvider
from backend.utils.llm.factory import current_provider

_COMPACT_SUFFIX = [(1e9, "B"), (1e6, "M"), (1e3, "K")]


def format_number(value: Any, currency: str = "") -> str:
    """Human-friendly compact number formatting (e.g. 8.2M)."""
    if value is None:
        return "N/A"
    if isinstance(value, str):
        return value
    try:
        v = float(value)
    except (TypeError, ValueError):
        return str(value)
    if math.isnan(v):
        return "N/A"
    sign = "-" if v < 0 else ""
    abs_v = abs(v)
    suffix = ""
    for cutoff, suf in _COMPACT_SUFFIX:
        if abs_v >= cutoff:
            abs_v /= cutoff
            suffix = suf
            break
    if abs_v.is_integer() and abs_v >= 100:
        num = f"{int(abs_v):,}"
    else:
        num = f"{abs_v:.1f}".rstrip("0").rstrip(".")
    return f"{sign}{currency}{num}{suffix}"


class InsightAgent:
    """Builds the explainable, insight-rich answer payload."""

    def __init__(self, llm: Optional[LLMProvider] = None) -> None:
        self.llm: LLMProvider = llm or current_provider
        self.mode: str = "deterministic"

    # ------------------------------------------------------------------ #
    def generate(
        self,
        question: str,
        plan: ExecutionPlan,
        outcome: AnalysisOutcome,
        validation: ValidationReport,
        llm_mode: str,
    ) -> Dict[str, Any]:
        """Produce the answer/insight/recommendation/confidence payload."""
        currency = _detect_currency(question)
        answer = self._build_answer(question, plan, outcome, currency)
        facts = self._facts_payload(outcome)

        if self.llm.available:
            generated = self._generate_with_llm(question, plan, facts, validation, currency)
            if generated:
                self.mode = "llm"
                insight, recommendation, text, follow_ups, structured = generated
                confidence = _confidence(validation, plan)
                return {
                    "answer": answer,
                    "text": text or self._deterministic_text(plan, answer, outcome),
                    "insight": insight,
                    "recommendation": recommendation,
                    "structured": structured,
                    "confidence": confidence,
                    "follow_ups": follow_ups,
                    "llm_mode": "llm",
                }

        self.mode = "deterministic"
        text = self._deterministic_text(plan, answer, outcome)
        insight, recommendation = self._deterministic_insight(question, plan, outcome, currency)
        structured = self._deterministic_structured(question, plan, outcome, answer, currency)
        return {
            "answer": answer,
            "text": text,
            "insight": insight,
            "recommendation": recommendation,
            "structured": structured,
            "confidence": _confidence(validation, plan),
            "follow_ups": self._deterministic_followups(question, plan),
            "llm_mode": "deterministic",
        }

    # ------------------------------------------------------------------ #
    def _build_answer(self, question: str, plan: ExecutionPlan, outcome: AnalysisOutcome,
                      currency: str) -> Dict[str, Any]:
        """Headline answer derived from the computed answer table."""
        intent = plan.intent
        answer: Dict[str, Any] = {
            "label": "",
            "value": "",
            "detail": "",
            "pairs": [],
            "intent": intent,
        }
        table = outcome.answer_table
        if not table:
            return answer

        rows = table.get("rows", [])
        cols = table.get("columns", [])
        if not rows:
            return answer

        # Prefer intent-specific extraction, fall back to first row.
        if intent in ("top", "compare", "total", "share"):
            row0 = rows[0]
            label_col, value_col = _split_dim_metric(cols)
            if label_col and value_col:
                answer["label"] = str(row0.get(label_col, ""))
                answer["value"] = format_number(row0.get(value_col), currency)
                answer["detail"] = f"{value_col} (aggregated from {outcome.answer_tool})"
                answer["pairs"] = [
                    {"k": str(c), "v": format_number(row0.get(c), currency)
                     if _is_number(row0.get(c)) else str(row0.get(c))}
                    for c in cols
                ]
                return answer
        if intent == "trend":
            trend = self._trend_headline(table, currency)
            if trend:
                answer["label"] = trend["label"]
                answer["value"] = trend["value"]
                answer["detail"] = trend["detail"]
                answer["pairs"] = trend["pairs"]
                return answer
        if intent == "growth":
            growth_rows = [r for r in rows if r.get("growth_%") is not None]
            if growth_rows:
                growth_rows = sorted(growth_rows, key=lambda r: float(r.get("growth_%") or 0), reverse=True)
                best = growth_rows[0]
                label_col = next((c for c in cols if c != "growth_%" and c != "growth%"), cols[0])
                answer["label"] = str(best.get(label_col, ""))
                answer["value"] = f"{best.get('growth_%'):+.1f}%"
                answer["detail"] = "period-over-period growth"
                answer["pairs"] = [{"k": str(c), "v": best.get(c)} for c in cols]
                return answer
        if intent == "correlation":
            coefficient = self._find_coefficient(outcome)
            if coefficient:
                r = coefficient["r"]
                strength = coefficient.get("strength", "weak")
                answer["label"] = f"{strength} correlation"
                answer["value"] = f"{r:+.2f}"
                answer["detail"] = (f"Pearson r between {coefficient['x']} "
                                    f"and {coefficient['y']}")
                answer["pairs"] = [
                    {"k": f"Pearson r ({coefficient['x']} vs {coefficient['y']})", "v": r},
                ]
                return answer
        if intent == "margin":
            row = self._margin_row(table)
            if row:
                answer["label"] = "Profit margin"
                answer["value"] = f"{row.get('profit_margin_%', 0):.2f}%"
                answer["detail"] = "profit / revenue x 100"
                answer["pairs"] = [
                    {"k": k, "v": v} for k, v in row.items()
                    if isinstance(v, (int, float))
                ]
                return answer

        # Fallback: first row, first dimension + numeric value
        label_col, value_col = _split_dim_metric(cols)
        if label_col and value_col:
            answer["label"] = str(rows[0].get(label_col, ""))
            answer["value"] = format_number(rows[0].get(value_col), currency)
            answer["detail"] = f"{value_col} (from {outcome.answer_tool})"
            answer["pairs"] = [{"k": str(c), "v": rows[0].get(c)} for c in cols]
            return answer
        return answer

    # ------------------------------------------------------------------ #
    def _trend_headline(self, table: Optional[Dict[str, Any]], currency: str) -> Optional[Dict]:
        """Summarise a time-series table as first -> last with % change.

        Pure formatting of pandas-computed values; no invented numbers.
        """
        if not table:
            return None
        cols = table.get("columns", [])
        rows = table.get("rows", [])
        if len(rows) < 2:
            return None
        metric_col = next((c for c in cols if _is_number(rows[0].get(c))), None)
        if not metric_col:
            return None
        first = rows[0].get(metric_col)
        last = rows[-1].get(metric_col)
        if first is None or last is None:
            return None
        pct = ((last - first) / first * 100) if first else 0.0
        date_col = next((c for c in cols if c != metric_col), None)
        first_label = rows[0].get(date_col) if date_col else "start"
        last_label = rows[-1].get(date_col) if date_col else "end"
        direction = "up" if pct > 0 else "down"
        return {
            "label": f"{metric_col} trend",
            "value": f"{format_number(first, currency)} -> {format_number(last, currency)}",
            "detail": f"{first_label} vs {last_label} ({direction} {abs(pct):.1f}%)",
            "pairs": [
                {"k": f"{metric_col} @ {first_label}", "v": format_number(first, currency)},
                {"k": f"{metric_col} @ {last_label}", "v": format_number(last, currency)},
                {"k": f"change ({direction})", "v": f"{pct:+.1f}%"},
            ],
        }

    # ------------------------------------------------------------------ #
    def _find_coefficient(self, outcome: AnalysisOutcome) -> Optional[Dict[str, Any]]:
        """Look up a correlation coefficient attached to any executed step."""
        for exec_ in outcome.executions:
            if not exec_.success or not exec_.result:
                continue
            extras = exec_.result.get("extras") or {}
            coeff = extras.get("coefficient")
            if coeff:
                return coeff
        return None

    def _margin_row(self, table: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Find the best margin row from either margin table shape."""
        if not table:
            return None
        rows, cols = table.get("rows", []), table.get("columns", [])
        if "metric" in cols:  # summary shape
            for r in rows:
                if r.get("metric") == "profit_margin_%":
                    return {"profit_margin_%": r.get("value")}
            return None
        if "profit_margin_%" in cols:  # grouped shape
            valid = [r for r in rows if r.get("profit_margin_%") is not None]
            if valid:
                return max(valid, key=lambda r: r.get("profit_margin_%"))
        return None

    # ------------------------------------------------------------------ #
    def _facts_payload(self, outcome: AnalysisOutcome) -> List[Dict[str, Any]]:
        """Flatten all computed tables into a facts payload for the LLM."""
        facts: List[Dict[str, Any]] = []
        for exec_ in outcome.executions:
            if not exec_.success or not exec_.result:
                continue
            result = exec_.result
            if result.get("type") == "table":
                facts.append(
                    {
                        "tool": exec_.step.action,
                        "description": exec_.step.description,
                        "columns": result.get("table", {}).get("columns", []),
                        "rows": result.get("table", {}).get("rows", [])[:10],
                    }
                )
        return facts

    # ------------------------------------------------------------------ #
    # LLM-backed phrasing
    # ------------------------------------------------------------------ #
    def _generate_with_llm(self, question, plan, facts, validation, currency):
        facts_json = _json_dumps(facts)
        issues_summary = "; ".join(i.message for i in validation.issues if i.severity == "error")
        prompt = f"""You are the Insight Agent of a business-intelligence AI agent.
You write concise, professional business insights. You MUST NOT invent or compute
any numbers -- only reference values exactly as given in the computed facts below.

Question: "{question}"

Execution intent: {plan.intent}

Computed facts (from Pandas, authoritative):
{facts_json}

Return JSON ONLY:
{{
  "text": "2-4 sentence plain-English summary of what the data shows, referencing exact numbers.",
  "insight": "1-2 sentence business insight interpreting the numbers.",
  "recommendation": "1-2 sentence actionable recommendation.",
  "executive_summary": "3-4 sentence executive summary synthesizing the finding.",
  "key_findings": ["3-5 concise findings, each referencing exact numbers"],
  "recommendations": ["2-4 actionable recommendations"],
  "risks": ["1-3 risks visible in the data"],
  "opportunities": ["1-3 opportunities visible in the data"],
  "follow_ups": [
    {{"question": "suggested follow-up question", "reason": "why it is useful"}}
  ]
}}
"""
        data = self.llm.chat_json([{"role": "user", "content": prompt}])
        if not data:
            return None
        follow_ups = []
        for fu in data.get("follow_ups", []):
            if isinstance(fu, dict):
                follow_ups.append(
                    FollowUp(question=str(fu.get("question", "")), reason=str(fu.get("reason", "")))
                )
        structured = StructuredInsights(
            executive_summary=str(data.get("executive_summary", "")),
            key_findings=[str(x) for x in (data.get("key_findings") or [])],
            recommendations=[str(x) for x in (data.get("recommendations") or [])],
            risks=[str(x) for x in (data.get("risks") or [])],
            opportunities=[str(x) for x in (data.get("opportunities") or [])],
        )
        return (
            str(data.get("insight", "")),
            str(data.get("recommendation", "")),
            str(data.get("text", "")),
            follow_ups,
            structured,
        )

    # ------------------------------------------------------------------ #
    # Deterministic phrasing
    # ------------------------------------------------------------------ #
    def _deterministic_text(self, plan: ExecutionPlan, answer: Dict[str, Any],
                            outcome: AnalysisOutcome) -> str:
        done = sum(1 for e in outcome.executions if e.success)
        total = len(plan.steps) or 1
        head = f"The agent executed {done} of {total} planned steps ({plan.intent} analysis)."
        if answer.get("label"):
            head += f" The top result is {answer['label']} with {answer['value']}."
        return head

    def _deterministic_insight(self, question: str, plan: ExecutionPlan,
                               outcome: AnalysisOutcome, currency: str) -> tuple:
        intent = plan.intent
        insight, recommendation = "", ""
        table = outcome.answer_table
        if intent == "trend":
            head = self._trend_headline(table, currency)
            if head:
                insight = (f"Over the analysed period, {head['label']} moved from "
                           f"{head['pairs'][0]['v']} to {head['pairs'][1]['v']} "
                           f"({head['pairs'][2]['v']}).")
                recommendation = ("Continue monitoring the trend; pair it with growth "
                                  "analysis to spot accelerating or decelerating periods.")
        elif intent == "top" and table:
            rows, cols = table.get("rows", []), table.get("columns", [])
            if rows and len(cols) >= 2:
                label_col, value_col = _split_dim_metric(cols)
                top = rows[0]
                insight = f"{top.get(label_col)} leads all groups with {format_number(top.get(value_col), currency)}."
                recommendation = (f"Investigate what drives success in {top.get(label_col)} "
                                  f"and replicate it across other groups.")
        elif intent == "growth":
            g_rows = [r for r in (table.get("rows", []) if table else []) if r.get("growth_%") is not None]
            if g_rows:
                best = max(g_rows, key=lambda r: r.get("growth_%") or 0)
                worst = min(g_rows, key=lambda r: r.get("growth_%") or 0)
                insight = (f"Strongest growth was {best.get('growth_%'):+.1f}% "
                           f"({best.get(next(c for c in best if c != 'growth_%'), 'period')}), "
                           f"while the weakest was {worst.get('growth_%'):+.1f}%.")
                recommendation = "Analyse the drivers behind the strongest growth period and address any declining periods."
        elif intent == "correlation":
            coeff = self._find_coefficient(outcome)
            if coeff:
                r = coeff["r"]
                direction = "positive" if r > 0 else "negative"
                insight = (f"There is a {coeff.get('strength', 'moderate')} {direction} "
                           f"linear relationship between {coeff['x']} and {coeff['y']} "
                           f"(Pearson r = {r:+.2f}).")
                recommendation = ("Treat this as association, not causation; "
                                  "investigate confounders before acting.")
        elif intent == "margin":
            row = self._margin_row(table)
            if row:
                m = row.get("profit_margin_%")
                insight = f"The profit margin is {m:.2f}%."
                recommendation = ("Monitor margin over time; a shrinking margin "
                                  "signals rising cost pressure.")
        elif intent in ("compare", "total", "share"):
            rows, cols = (table.get("rows", []), table.get("columns", [])) if table else ([], [])
            if rows and len(cols) >= 2:
                label_col, value_col = _split_dim_metric(cols)
                spread = [r.get(value_col) for r in rows if r.get(value_col) is not None]
                if spread:
                    diff = max(spread) - min(spread)
                    insight = (f"{rows[0].get(label_col)} leads with "
                               f"{format_number(rows[0].get(value_col), currency)}; the gap to the "
                               f"smallest group is {format_number(diff, currency)}.")
                    recommendation = "Prioritise the highest-performing segment while investigating laggards."
        if not insight:
            insight = ("The data was analysed and summarized. Review the supporting tables and "
                       "charts for the full breakdown.")
            recommendation = "Explore a follow-up question to dig deeper into a specific dimension."
        return insight, recommendation

    def _deterministic_followups(self, question: str, plan: ExecutionPlan) -> List[FollowUp]:
        intent = plan.intent
        base = {
            "top": FollowUp(question="How has the leader changed over the last 4 quarters?",
                            reason="Checks whether the ranking is stable or temporary."),
            "trend": FollowUp(question="Which segment is growing fastest within this trend?",
                              reason="Locates the driver of the overall trend."),
            "growth": FollowUp(question="Which groups showed negative growth?",
                               reason="Identifies underperformers worth investigating."),
            "compare": FollowUp(question="What drives the difference between the top two groups?",
                                reason="Explains the source of the gap."),
            "correlation": FollowUp(question="Does the relationship hold across time periods?",
                                    reason="Tests robustness of the correlation."),
            "margin": FollowUp(question="How does profit margin trend by quarter?",
                               reason="Reveals margin compression over time."),
            "yoy": FollowUp(question="Which product category showed the strongest YoY growth?",
                            reason="Locates the biggest annual movers."),
            "mode": FollowUp(question="How does the most common value change over time?",
                             reason="Checks whether the mode is stable."),
        }
        fu = base.get(intent)
        if fu:
            return [fu]
        return [FollowUp(question="Show me the monthly trend for the same metric.",
                         reason="Adds time context to the result.")]

    # ------------------------------------------------------------------ #
    def _deterministic_structured(
        self,
        question: str,
        plan: ExecutionPlan,
        outcome: AnalysisOutcome,
        answer: Dict[str, Any],
        currency: str,
    ) -> StructuredInsights:
        """Build executive-grade structured insights from computed facts only."""
        intent = plan.intent
        table = outcome.answer_table
        rows, cols = (table.get("rows", []), table.get("columns", [])) if table else ([], [])

        findings: List[str] = []
        risks: List[str] = []
        opportunities: List[str] = []
        recommendations: List[str] = []

        if answer.get("label"):
            findings.append(
                f"{answer['label']} leads with {answer['value']} ({answer.get('detail') or intent})."
            )

        if intent == "trend":
            head = self._trend_headline(table, currency)
            if head:
                findings.append(
                    f"{head['label']} moved from {head['pairs'][0]['v']} to "
                    f"{head['pairs'][1]['v']} ({head['pairs'][2]['v']})."
                )
                if "-" in head["pairs"][2]["v"]:
                    risks.append("The metric is declining; investigate the underlying drivers.")
                    recommendations.append("Diagnose the cause of the decline before the trend accelerates.")
                else:
                    opportunities.append("The metric is growing; capitalise on the momentum.")
                    recommendations.append("Sustain the growth drivers and scale what is working.")
        elif intent == "growth":
            g_rows = [r for r in rows if r.get("growth_%") is not None]
            if g_rows:
                best = max(g_rows, key=lambda r: r.get("growth_%") or 0)
                worst = min(g_rows, key=lambda r: r.get("growth_%") or 0)
                findings.append(f"Best growth period: {best.get('growth_%'):+.1f}%.")
                findings.append(f"Weakest growth period: {worst.get('growth_%'):+.1f}%.")
                opportunities.append("Replicate the conditions of the best growth period.")
                risks.append("Watch the weakest period; volatility may signal instability.")
        elif intent == "correlation":
            coeff = self._find_coefficient(outcome)
            if coeff:
                findings.append(
                    f"Pearson r = {coeff['r']:+.2f} between {coeff['x']} and {coeff['y']} "
                    f"({coeff.get('strength', 'moderate')})."
                )
                if abs(coeff["r"]) < 0.3:
                    risks.append("The relationship is weak; do not over-index on it.")
        elif intent in ("top", "compare", "total", "share", "average", "median"):
            if rows and len(cols) >= 2:
                label_col, value_col = _split_dim_metric(cols)
                spread = [r.get(value_col) for r in rows if r.get(value_col) is not None]
                if spread:
                    findings.append(
                        f"Range across groups: {format_number(min(spread), currency)} to "
                        f"{format_number(max(spread), currency)}."
                    )
                    gap = max(spread) - min(spread)
                    if gap > 0:
                        recommendations.append(
                            f"Close the {format_number(gap, currency)} gap between the "
                            f"top and bottom groups."
                        )
        elif intent == "margin":
            row = self._margin_row(table)
            if row:
                m = row.get("profit_margin_%")
                findings.append(f"Profit margin is {m:.2f}%.")
                recommendations.append("Track margin trend; a shrinking margin signals cost pressure.")
                risks.append("Margin below 20% leaves little buffer for cost shocks.")
                opportunities.append("Optimise costs to expand margin headroom.")

        if not findings:
            findings.append("Review the supporting tables for the full breakdown.")

        summary = (findings[0] if findings else "") + (
            " The analysis used Pandas computations; no values were estimated."
        )

        if not recommendations:
            recommendations.append("Explore a follow-up question to go deeper on a dimension.")
        if not risks:
            risks.append("No immediate risk detected in the computed data.")
        if not opportunities:
            opportunities.append("Run a trend or growth question to find opportunities.")

        return StructuredInsights(
            executive_summary=summary,
            key_findings=findings,
            recommendations=recommendations,
            risks=risks,
            opportunities=opportunities,
        )


def _detect_currency(question: str) -> str:
    if re.search(r"₹|rupee|inr|indian", question, re.IGNORECASE):
        return "₹"
    if re.search(r"[$€£]", question):
        return "$"
    return "₹"


def _confidence(validation: ValidationReport, plan: ExecutionPlan) -> float:
    errors = sum(1 for i in validation.issues if i.severity == "error")
    warnings = sum(1 for i in validation.issues if i.severity == "warning")
    infos = sum(1 for i in validation.issues if i.severity == "info")
    corrections = len(validation.corrections)
    score = 0.99 - 0.04 * warnings - 0.02 * infos - 0.03 * corrections
    if errors > 0:
        score = min(score, 0.35)
    return round(min(max(score, 0.05), 0.99), 2)


def _split_dim_metric(cols: List[str]) -> tuple:
    """Split table columns into (dimension, metric)."""
    if not cols:
        return None, None
    dim_candidates = [c for c in cols if _looks_dimensional(c)]
    if dim_candidates and len(cols) >= 2:
        dim = dim_candidates[0]
        metric = next((c for c in cols if c != dim and _metric_like(c)), None)
        return dim, metric or cols[-1]
    if len(cols) >= 2:
        return cols[0], cols[1]
    return cols[0], cols[0]


def _looks_dimensional(col: str) -> bool:
    low = col.lower()
    if any(k in low for k in ("revenue", "profit", "sales", "amount", "price", "cost", "margin", "growth", "count", "sum", "mean", "median", "value", "rolling")):
        return False
    return True


def _metric_like(col: str) -> bool:
    low = col.lower()
    return any(k in low for k in ("revenue", "profit", "sales", "amount", "price", "cost", "margin", "growth", "count", "sum", "mean", "median", "value", "rolling", "qty", "quantity"))


def _is_number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _json_dumps(data: Any) -> str:
    import json

    return json.dumps(data, default=str, ensure_ascii=False)


insight_agent = InsightAgent()
