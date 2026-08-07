"""Agent 5 - Visualization Agent.

Automatically picks a chart type for each answer table using rule-based
mapping (trend -> line, comparison -> bar, distribution -> histogram,
correlation -> scatter, share -> pie) and renders interactive Plotly figures.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from backend.agents.analysis_agent import AnalysisOutcome
from backend.tools import chart_tools
from backend.models.schemas import ChartSpec

_CHART_RATIONALE = {
    "line": "Line charts reveal trends and changes over time.",
    "bar": "Bar charts compare magnitudes across categories.",
    "pie": "Pie charts show the share of each category in a total.",
    "scatter": "Scatter plots expose relationships between two numeric variables.",
    "histogram": "Histograms describe the distribution of a single variable.",
    "heatmap": "Heatmaps visualise correlation or pivot matrices.",
}


class VisualizationAgent:
    """Renders chart specs for the agent's computed tables."""

    def visualize(self, outcome: AnalysisOutcome, question: str = "") -> List[ChartSpec]:
        specs: List[ChartSpec] = []
        for exec_ in outcome.executions:
            if not exec_.success or not exec_.result:
                continue
            result = exec_.result
            if result.get("type") != "table":
                continue
            table = result.get("table", {})
            if not table.get("rows"):
                continue

            hint = str(result.get("chart_hint") or "")
            chart_type = chart_tools.select_chart_type(
                hint, exec_.step.action, table, question
            )
            meta = {"tool": exec_.step.action}
            fig = chart_tools.render_chart(chart_type, table, meta, question)
            if fig is None:
                continue

            specs.append(
                ChartSpec(
                    chart_type=chart_type,
                    title=(question.strip().rstrip(".") or exec_.step.description)[:80],
                    rationale=_CHART_RATIONALE.get(chart_type, "Auto-selected chart."),
                    plotly_json=fig,
                )
            )
        return specs


visualization_agent = VisualizationAgent()
