"""Chart selection and Plotly figure generation.

The Visualization Agent decides *which* chart best answers a question and this
module turns computed pandas results into interactive Plotly JSON figures.
Rule-based chart selection (trend -> line, comparison -> bar, distribution ->
histogram, correlation -> scatter, share -> pie) keeps charting deterministic.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import plotly.graph_objects as go


# --------------------------------------------------------------------------- #
# Chart type selection
# --------------------------------------------------------------------------- #
def select_chart_type(
    hint: str,
    tool_name: str,
    table: Optional[Dict[str, Any]] = None,
    question: str = "",
) -> str:
    """Choose a Plotly chart type from a tool hint and the question text."""
    q = question.lower()
    if "correlat" in q or "relationship" in q or "correlation" in tool_name:
        return "scatter"
    if "trend" in q or "over time" in q or "monthly" in q or "growth" in q:
        return "line"
    if hint == "line":
        return "line"
    if "distribut" in q or "histogram" in q:
        return "histogram"
    if "share" in q or "proportion" in q or "pie" in q or hint == "pie":
        return "pie"
    if hint == "scatter":
        return "scatter"
    if hint == "bar" or "compare" in q or "top" in q or "best" in q or "highest" in q:
        return "bar"
    if hint == "histogram":
        return "histogram"
    if "correlation" in tool_name:
        return "scatter"
    # Fallback by table shape
    if table and len(table.get("columns", [])) >= 2:
        if table.get("row_count", 0) > 1 and len(table["columns"]) == 2:
            return "bar"
    return "bar"


# --------------------------------------------------------------------------- #
# Figure builders
# --------------------------------------------------------------------------- #
def _fmt(v: Any) -> str:
    if v is None:
        return "N/A"
    if isinstance(v, float):
        return f"{v:,.2f}"
    return str(v)


def build_line(df, x_col: str, y_cols: List[str], title: str) -> Dict[str, Any]:
    fig = go.Figure()
    for y in y_cols:
        fig.add_trace(go.Scatter(x=df[x_col], y=df[y], mode="lines+markers", name=str(y)))
    fig.update_layout(title=title, template="plotly_dark", height=420)
    return fig.to_plotly_json()


def build_bar(df, x_col: str, y_cols: List[str], title: str, orientation: str = "v") -> Dict[str, Any]:
    fig = go.Figure()
    for y in y_cols:
        if orientation == "h":
            fig.add_trace(go.Bar(x=df[y], y=df[x_col], name=str(y), orientation="h"))
        else:
            fig.add_trace(go.Bar(x=df[x_col], y=df[y], name=str(y)))
    fig.update_layout(title=title, template="plotly_dark", height=420)
    return fig.to_plotly_json()


def build_pie(labels, values, title: str) -> Dict[str, Any]:
    fig = go.Figure(go.Pie(labels=labels, values=values, hole=0.45))
    fig.update_layout(title=title, template="plotly_dark", height=420)
    return fig.to_plotly_json()


def build_scatter(x, y, title: str) -> Dict[str, Any]:
    fig = go.Figure(go.Scatter(x=x, y=y, mode="markers", marker=dict(size=9)))
    fig.update_layout(title=title, template="plotly_dark", height=420)
    return fig.to_plotly_json()


def build_histogram(values, title: str) -> Dict[str, Any]:
    fig = go.Figure(go.Histogram(x=values, nbinsx=30))
    fig.update_layout(title=title, template="plotly_dark", height=420)
    return fig.to_plotly_json()


def build_heatmap(matrix_df, title: str) -> Dict[str, Any]:
    fig = go.Figure(
        go.Heatmap(
            z=matrix_df.values,
            x=[str(c) for c in matrix_df.columns],
            y=[str(i) for i in matrix_df.index],
            colorscale="Viridis",
        )
    )
    fig.update_layout(title=title, template="plotly_dark", height=420)
    return fig.to_plotly_json()


# --------------------------------------------------------------------------- #
# Orchestrator
# --------------------------------------------------------------------------- #
def render_chart(
    chart_type: str,
    table: Dict[str, Any],
    meta: Dict[str, Any],
    question: str = "",
) -> Optional[Dict[str, Any]]:
    """Build a Plotly figure from a result table.

    Args:
        chart_type: one of bar/line/pie/scatter/histogram/heatmap.
        table: JSON table produced by the Analysis Agent.
        meta: contextual metadata (tool name, column hints).
        question: original question text (used for titles).

    Returns:
        Plotly figure JSON, or None if the table is not chartable.
    """
    columns = table.get("columns", [])
    rows = table.get("rows", [])
    if not columns or not rows:
        return None

    title = _make_title(meta, question)
    try:
        if chart_type == "heatmap":
            import pandas as pd

            df = pd.DataFrame(rows)
            df = df.set_index(columns[0]) if columns[0] in df.columns else df
            return build_heatmap(df, title)

        if chart_type == "scatter":
            if len(columns) >= 2:
                x = [r[columns[0]] for r in rows]
                y = [r[columns[1]] for r in rows]
                return build_scatter(x, y, title)
            return None

        if chart_type == "histogram":
            num_cols = [c for c in columns if _is_numeric_list(rows, c)]
            if num_cols:
                return build_histogram([r[num_cols[0]] for r in rows], title)
            return None

        if chart_type == "pie":
            if len(columns) >= 2:
                labels = [str(r[columns[0]]) for r in rows]
                num_cols = [c for c in columns if c != columns[0] and _is_numeric_list(rows, c)]
                if not num_cols:
                    return None
                values = [r[num_cols[0]] for r in rows]
                if not values or sum(v or 0 for v in values) == 0:
                    return None
                return build_pie(labels, values, title)

        # bar / line fallback
        num_cols = [c for c in columns if _is_numeric_list(rows, c)]
        if not num_cols:
            return None
        x_col = _pick_x_col(columns, num_cols)
        y_cols = num_cols
        if len(rows) > 40:
            rows = rows[:40]
        return build_bar(_rows_to_df(rows), x_col, y_cols, title)
    except Exception:
        return None


def _rows_to_df(rows: List[Dict[str, Any]]) -> Dict[str, List[Any]]:
    """Convert row dicts into a column-first dict for plotly."""
    keys = list(rows[0].keys()) if rows else []
    return {k: [r.get(k) for r in rows] for k in keys}


def _is_numeric_list(rows: List[Dict[str, Any]], col: str) -> bool:
    vals = [r.get(col) for r in rows if r.get(col) is not None]
    if not vals:
        return False
    numeric = [v for v in vals if isinstance(v, (int, float))]
    if numeric:
        return len(numeric) / len(vals) >= 0.8
    return False


def _pick_x_col(columns: List[str], num_cols: List[str]) -> str:
    """Pick the most likely x-axis column (non-numeric first)."""
    for c in columns:
        if c not in num_cols:
            return c
    return columns[0]


def _make_title(meta: Dict[str, Any], question: str) -> str:
    tool = meta.get("tool", "")
    if question:
        return question.strip().rstrip(".")[:80]
    return f"{tool.replace('_', ' ').title()} result"
