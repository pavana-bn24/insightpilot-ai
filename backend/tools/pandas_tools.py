"""Pandas-powered computation registry.

This is the *only* place numbers are computed in InsightPilot. The LLM never
performs arithmetic -- it plans against these registered tools and the
Analysis Agent executes them. Each tool is a pure function over a DataFrame
plus metadata that downstream agents (validation, visualization, insight) use.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

import pandas as pd

from backend.tools import similarity
from backend.tools.data_loader import DataLoadError


class ToolError(Exception):
    """Raised when a computation tool fails (invalid params / missing data)."""


@dataclass
class ToolSpec:
    """Registry metadata for one computation tool."""

    name: str
    fn: Callable[..., Any]
    description: str
    required_params: List[str] = field(default_factory=list)
    returns: str = "result"
    produces_table: bool = True
    produces_chart: bool = False
    chart_hint: str = ""


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _to_list(series: pd.Series, limit: int = 50) -> List[Any]:
    """Convert a Series to a JSON-safe list (resolving numpy types)."""
    out: List[Any] = []
    for v in series.head(limit).tolist():
        if pd.isna(v):
            out.append(None)
        elif hasattr(v, "item"):
            try:
                out.append(v.item())
            except Exception:
                out.append(v)
        else:
            out.append(v)
    return out


def _table(df: pd.DataFrame, limit: int = 50) -> Dict[str, Any]:
    """Render a DataFrame as a JSON-ready table."""
    if df.empty:
        return {"columns": [], "rows": [], "row_count": 0}
    rows = []
    for _, row in df.head(limit).iterrows():
        rows.append(
            {
                str(col): _to_list(pd.Series([row[col]]))[0] if False else (
                    None if pd.isna(row[col]) else (
                        row[col].item() if hasattr(row[col], "item") and not isinstance(row[col], str) else row[col]
                    )
                )
                for col in df.columns
            }
        )
    return {
        "columns": [str(c) for c in df.columns],
        "rows": rows,
        "row_count": int(len(df)),
    }


def _value(v: Any) -> Any:
    if pd.isna(v):
        return None
    if hasattr(v, "item") and not isinstance(v, str):
        try:
            return v.item()
        except Exception:
            return v
    return v


def _resolve_col(df: pd.DataFrame, requested: str) -> str:
    """Resolve a column name against the DataFrame (exact -> fuzzy)."""
    if requested in df.columns:
        return requested
    resolved = similarity.closest_column(requested, list(df.columns))
    if resolved:
        return resolved
    raise ToolError(f"Column '{requested}' not found in dataset.")


def _pct_change(first: float, second: float) -> Optional[float]:
    if first is None or second is None:
        return None
    if first == 0:
        return None
    return (second - first) / first


# --------------------------------------------------------------------------- #
# Core tools
# --------------------------------------------------------------------------- #
def t_filter(df: pd.DataFrame, column: str, condition: str, value: Any) -> pd.DataFrame:
    """Filter rows by condition against a column."""
    col = _resolve_col(df, column)
    series = df[col]
    if condition == "eq":
        mask = series == value
    elif condition == "neq":
        mask = series != value
    elif condition == "gt":
        mask = pd.to_numeric(series, errors="coerce") > float(value)
    elif condition == "gte":
        mask = pd.to_numeric(series, errors="coerce") >= float(value)
    elif condition == "lt":
        mask = pd.to_numeric(series, errors="coerce") < float(value)
    elif condition == "lte":
        mask = pd.to_numeric(series, errors="coerce") <= float(value)
    elif condition == "in":
        mask = series.isin(value) if isinstance(value, list) else series == value
    elif condition == "contains":
        mask = series.astype(str).str.contains(str(value), case=False, na=False)
    else:
        raise ToolError(f"Unknown filter condition '{condition}'.")
    return df[mask]


def t_group_agg(
    df: pd.DataFrame,
    group_by: str,
    aggregate: str = "sum",
    metric: Optional[str] = None,
) -> pd.DataFrame:
    """Group by a column and aggregate a metric column."""
    group_col = _resolve_col(df, group_by)
    if metric is None:
        numeric = _pick_metric(df)
    else:
        numeric = _resolve_col(df, metric)
    agg_map = {
        "sum": "sum", "mean": "mean", "median": "median",
        "max": "max", "min": "min", "count": "count", "std": "std",
    }
    if aggregate not in agg_map:
        raise ToolError(f"Unsupported aggregation '{aggregate}'.")
    grouped = (
        df.groupby(group_col, observed=True)[numeric]
        .agg(agg_map[aggregate])
        .reset_index()
        .rename(columns={numeric: f"{numeric}_{aggregate}"})
    )
    return grouped.sort_values(f"{numeric}_{aggregate}", ascending=False)


def t_pick_metric(df: pd.DataFrame, metric: Optional[str] = None) -> str:
    """Resolve the metric column for a query."""
    if metric:
        return _resolve_col(df, metric)
    candidates = similarity.pick_metric(list(df.columns))
    if candidates:
        return candidates
    numeric = df.select_dtypes(include="number").columns.tolist()
    if numeric:
        return numeric[-1]
    raise ToolError("No numeric metric column found in dataset.")


def t_sort(df: pd.DataFrame, column: str, ascending: bool = False) -> pd.DataFrame:
    col = _resolve_col(df, column)
    return df.sort_values(col, ascending=ascending).reset_index(drop=True)


def t_top_n(df: pd.DataFrame, column: str, n: int = 5) -> pd.DataFrame:
    col = _resolve_col(df, column)
    return t_sort(df, col, ascending=False).head(int(n)).reset_index(drop=True)


def t_bottom_n(df: pd.DataFrame, column: str, n: int = 5) -> pd.DataFrame:
    col = _resolve_col(df, column)
    return t_sort(df, col, ascending=True).head(int(n)).reset_index(drop=True)


def t_head(df: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    return df.head(int(n)).reset_index(drop=True)


def t_describe(df: pd.DataFrame, column: Optional[str] = None) -> pd.DataFrame:
    if column:
        col = _resolve_col(df, column)
        return df[[col]].describe(percentiles=[0.25, 0.5, 0.75])
    return df.describe(percentiles=[0.25, 0.5, 0.75])


def t_value_counts(df: pd.DataFrame, column: str, n: int = 10) -> pd.DataFrame:
    col = _resolve_col(df, column)
    vc = df[col].value_counts().head(int(n)).reset_index()
    vc.columns = [col, "count"]
    return vc


def t_correlation(df: pd.DataFrame, x: Optional[str] = None, y: Optional[str] = None) -> Any:
    """Pearson correlation between two columns (or a full matrix).

    For a two-column request it returns ``(points_df, extras)`` where
    ``points_df`` holds sampled data points (for a scatter chart) and ``extras``
    carries the computed coefficient. Without x/y it returns the full
    correlation matrix.
    """
    numeric = df.select_dtypes(include="number")
    if x and y:
        xc, yc = _resolve_col(df, x), _resolve_col(df, y)
        if xc not in numeric.columns or yc not in numeric.columns:
            raise ToolError(f"Correlation requires numeric columns; got '{xc}', '{yc}'.")
        clean = df[[xc, yc]].dropna()
        if clean.empty:
            raise ToolError("No overlapping non-null values for correlation.")
        r = float(clean.corr().iloc[0, 1])
        points = clean.sample(min(300, len(clean)), random_state=1).reset_index(drop=True)
        extras = {"coefficient": {"x": xc, "y": yc, "r": r,
                                  "strength": "strong" if abs(r) >= 0.7 else (
                                      "moderate" if abs(r) >= 0.4 else "weak")}}
        return points, extras
    if numeric.shape[1] < 2:
        raise ToolError("Need at least two numeric columns for correlation.")
    return numeric.corr().round(4)


def t_pivot(
    df: pd.DataFrame,
    index: str,
    columns: str,
    values: str,
    aggfunc: str = "sum",
) -> pd.DataFrame:
    idx, col_col, val_col = (
        _resolve_col(df, index),
        _resolve_col(df, columns),
        _resolve_col(df, values),
    )
    func = {"sum": "sum", "mean": "mean", "count": "count", "median": "median"}.get(aggfunc, "sum")
    piv = df.pivot_table(index=idx, columns=col_col, values=val_col, aggfunc=func, fill_value=0)
    piv = piv.reset_index()
    piv.columns = [str(c) for c in piv.columns]
    return piv


def t_growth(
    df: pd.DataFrame,
    time_col: str,
    value_col: str,
    group_col: Optional[str] = None,
    period: str = "M",
) -> pd.DataFrame:
    """Compute period-over-period percentage growth for a metric.

    Returns a DataFrame with a date/period column, the summed metric and a
    ``growth_%`` column. Growth is rounded, and the first period has ``None``
    (no previous period to compare against) -- the Validation Agent handles it.
    """
    tc = _resolve_col(df, time_col)
    vc = _resolve_col(df, value_col)
    if not pd.api.types.is_datetime64_any_dtype(df[tc].dtype):
        df = df.copy()
        df[tc] = pd.to_datetime(df[tc], errors="coerce")
    df = df.dropna(subset=[tc, vc])
    if df.empty:
        raise ToolError("No valid rows after parsing dates for growth analysis.")

    freq = {"D": "D", "W": "W-MON", "M": "M", "Q": "Q", "Y": "Y"}.get(
        period.upper(), "M"
    )

    if group_col:
        gc = _resolve_col(df, group_col)
        df["_period"] = df[tc].dt.to_period(freq)
        grouped = df.groupby([gc, "_period"], observed=True)[vc].sum().reset_index()
        out = []
        for group_name, sub in grouped.groupby(gc, observed=True):
            sub = sub.sort_values("_period")
            sub["growth_%"] = (
                (sub[vc] - sub[vc].shift(1)) / sub[vc].shift(1).replace(0, pd.NA) * 100
            ).round(2)
            sub[vc] = sub[vc].round(2)
            out.append(sub)
        result = pd.concat(out, ignore_index=True)
        result["_period"] = result["_period"].astype(str)
        return result.rename(columns={"_period": f"{tc}_period"})

    df["_period"] = df[tc].dt.to_period(freq)
    g = df.groupby("_period", observed=True)[vc].sum().reset_index()
    g = g.sort_values("_period")
    g["growth_%"] = (g[vc] - g[vc].shift(1)) / g[vc].shift(1).replace(0, pd.NA) * 100
    g["growth_%"] = g["growth_%"].round(2)
    g[vc] = g[vc].round(2)
    g["_period"] = g["_period"].astype(str)
    return g.rename(columns={"_period": f"{tc}_period"})


def t_time_series(
    df: pd.DataFrame,
    time_col: str,
    value_col: str,
    period: str = "M",
    aggfunc: str = "sum",
    group_col: Optional[str] = None,
) -> pd.DataFrame:
    """Resample a metric over time (daily/weekly/monthly/quarterly/yearly)."""
    tc = _resolve_col(df, time_col)
    vc = _resolve_col(df, value_col)
    if not pd.api.types.is_datetime64_any_dtype(df[tc].dtype):
        df = df.copy()
        df[tc] = pd.to_datetime(df[tc], errors="coerce")
    df = df.dropna(subset=[tc, vc])
    if df.empty:
        raise ToolError("No valid date rows for time series analysis.")

    freq = {"D": "D", "W": "W", "M": "ME", "Q": "QE", "Y": "YE", "H": "h"}.get(
        period.upper(), "ME"
    )
    agg = {"sum": "sum", "mean": "mean", "count": "count", "median": "median"}.get(aggfunc, "sum")

    if group_col:
        gc = _resolve_col(df, group_col)
        result = (
            df.set_index(tc)
            .groupby([gc, pd.Grouper(freq=freq)], observed=True)[vc]
            .agg(agg)
            .reset_index()
        )
    else:
        result = (
            df.set_index(tc)
            .groupby(pd.Grouper(freq=freq), observed=True)[vc]
            .agg(agg)
            .reset_index()
        )
    result.columns = [str(c) for c in result.columns]
    result[result.columns[0]] = result[result.columns[0]].astype(str)
    return result


def t_rolling(df: pd.DataFrame, column: str, window: int = 3) -> pd.DataFrame:
    """Moving average of a numeric column ordered by its natural order."""
    col = _resolve_col(df, column)
    out = df.copy()
    out["rolling_mean"] = pd.to_numeric(out[col], errors="coerce").rolling(
        int(window), min_periods=1
    ).mean().round(2)
    out["rolling_median"] = pd.to_numeric(out[col], errors="coerce").rolling(
        int(window), min_periods=1
    ).median().round(2)
    return out


def t_compare(
    df: pd.DataFrame,
    group_by: str,
    metric: Optional[str] = None,
    aggregate: str = "sum",
    groups: Optional[List[str]] = None,
) -> pd.DataFrame:
    """Compare aggregated metric across group values (optionally a subset)."""
    group_col = _resolve_col(df, group_by)
    metric_col = t_pick_metric(df, metric)
    sub = df
    if groups:
        sub = sub[sub[group_col].isin(groups)]
    agg_map = {
        "sum": "sum", "mean": "mean", "median": "median",
        "max": "max", "min": "min", "count": "count",
    }
    out = (
        sub.groupby(group_col, observed=True)[metric_col]
        .agg(agg_map.get(aggregate, "sum"))
        .reset_index()
    )
    out.columns = [group_col, f"{metric_col}_{aggregate}"]
    return out


def t_kpi_margin(
    df: pd.DataFrame,
    revenue_col: str,
    cost_col: str,
    group_by: Optional[str] = None,
) -> pd.DataFrame:
    """Compute profit = revenue - cost and profit margin %."""
    rev = _resolve_col(df, revenue_col)
    cost = _resolve_col(df, cost_col)
    margin_df = df.copy()
    margin_df["profit"] = margin_df[rev] - margin_df[cost]
    denominator = margin_df[rev].replace(0, pd.NA)
    margin_df["profit_margin_%"] = (margin_df["profit"] / denominator * 100).round(2)
    if group_by:
        gc = _resolve_col(df, group_by)
        out = (
            margin_df.groupby(gc, observed=True)
            .agg(revenue=(rev, "sum"), cost=(cost, "sum"))
            .reset_index()
        )
        out["profit"] = (out["revenue"] - out["cost"]).round(2)
        out["profit_margin_%"] = (out["profit"] / out["revenue"].replace(0, pd.NA) * 100).round(2)
        return out
    total_rev = float(margin_df[rev].sum())
    total_cost = float(margin_df[cost].sum())
    profit = total_rev - total_cost
    margin = (profit / total_rev * 100) if total_rev else 0.0
    return pd.DataFrame(
        {
            "metric": ["revenue", "cost", "profit", "profit_margin_%"],
            "value": [round(total_rev, 2), round(total_cost, 2), round(profit, 2), round(margin, 2)],
        }
    )


def t_insights(df: pd.DataFrame, metric_col: str) -> pd.DataFrame:
    """Compute a compact set of summary facts for the Insight Agent."""
    col = _resolve_col(df, metric_col)
    numeric = pd.to_numeric(df[col], errors="coerce").dropna()
    if numeric.empty:
        raise ToolError(f"Column '{col}' contains no usable numeric values.")
    return pd.DataFrame(
        {
            "metric": [col],
            "sum": [round(float(numeric.sum()), 2)],
            "mean": [round(float(numeric.mean()), 2)],
            "median": [round(float(numeric.median()), 2)],
            "std": [round(float(numeric.std()), 2)],
            "min": [round(float(numeric.min()), 2)],
            "max": [round(float(numeric.max()), 2)],
            "p90": [round(float(numeric.quantile(0.9)), 2)],
        }
    )


def t_mode(df: pd.DataFrame, column: str) -> pd.DataFrame:
    """Statistical mode (most frequent value) of a column."""
    col = _resolve_col(df, column)
    counts = df[col].value_counts().reset_index()
    counts.columns = [col, "count"]
    return counts.head(1)


def t_yoy(df: pd.DataFrame, time_col: str, value_col: str, group_col: Optional[str] = None) -> pd.DataFrame:
    """Year-over-year comparison: aggregate by year and compute YoY growth %.

    When ``group_col`` is given, YoY growth is computed per group and rows are
    sorted by the overall yearly change for readability.
    """
    tc = _resolve_col(df, time_col)
    vc = _resolve_col(df, value_col)
    if not pd.api.types.is_datetime64_any_dtype(df[tc].dtype):
        df = df.copy()
        df[tc] = pd.to_datetime(df[tc], errors="coerce")
    df = df.dropna(subset=[tc, vc])
    if df.empty:
        raise ToolError("No valid rows after parsing dates for YoY analysis.")

    df["_year"] = df[tc].dt.year

    if group_col:
        gc = _resolve_col(df, group_col)
        yearly = (
            df.groupby([gc, "_year"], observed=True)[vc]
            .sum()
            .reset_index()
        )
        yearly[vc] = yearly[vc].round(2)
        out = []
        for group_name, sub in yearly.groupby(gc, observed=True):
            sub = sub.sort_values("_year")
            prev = sub[vc].shift(1)
            sub["yoy_growth_%"] = ((sub[vc] - prev) / prev.replace(0, pd.NA) * 100).round(2)
            out.append(sub)
        result = pd.concat(out, ignore_index=True)
        result = result.sort_values(["yoy_growth_%"], ascending=False, na_position="last")
        return result

    yearly = df.groupby("_year", observed=True)[vc].sum().reset_index()
    yearly = yearly.sort_values("_year")
    yearly[vc] = yearly[vc].round(2)
    prev = yearly[vc].shift(1)
    yearly["yoy_growth_%"] = ((yearly[vc] - prev) / prev.replace(0, pd.NA) * 100).round(2)
    return yearly


def t_outliers(df: pd.DataFrame, column: str, factor: float = 1.5) -> pd.DataFrame:
    """IQR-based outlier detection on a numeric column.

    Returns a single summary table: the fence bounds plus the flagged outlier
    values as a list column.
    """
    col = _resolve_col(df, column)
    numeric = pd.to_numeric(df[col], errors="coerce")
    q1, q3 = numeric.quantile(0.25), numeric.quantile(0.75)
    iqr = q3 - q1
    if iqr == 0 or pd.isna(iqr):
        raise ToolError(f"Column '{col}' has no IQR spread; outlier detection skipped.")
    lower = q1 - factor * iqr
    upper = q3 + factor * iqr
    mask = numeric.between(lower, upper, inclusive="neither").fillna(False) & numeric.notna()
    outlier_values = [round(float(v), 2) for v in df.loc[~mask, col].tolist()[:20]]
    return pd.DataFrame(
        [
            {
                "column": col,
                "q1": round(float(q1), 2),
                "q3": round(float(q3), 2),
                "lower_fence": round(float(lower), 2),
                "upper_fence": round(float(upper), 2),
                "outlier_count": int(len(outlier_values)),
                "outlier_pct": round(float(len(outlier_values) / max(len(df), 1) * 100), 2),
                "sample_values": outlier_values,
            }
        ]
    )


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #
REGISTRY: Dict[str, ToolSpec] = {}


def register(name: str, description: str, produces_chart: bool = False, chart_hint: str = "", **kw):
    def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
        REGISTRY[name] = ToolSpec(
            name=name,
            fn=fn,
            description=description,
            required_params=kw.get("required_params", []),
            returns=kw.get("returns", "result"),
            produces_table=kw.get("produces_table", True),
            produces_chart=produces_chart,
            chart_hint=chart_hint,
        )
        return fn
    return deco


register("filter", "Filter rows by a condition", produces_chart=False, returns="dataframe")(t_filter)
register("group_agg", "Group by a column and aggregate a metric")(t_group_agg)
register("pick_metric", "Resolve the metric column for a query", produces_table=False)(t_pick_metric)
register("sort", "Sort rows by a column", produces_chart=False)(t_sort)
register("top_n", "Top N rows by a numeric column", chart_hint="bar")(t_top_n)
register("bottom_n", "Bottom N rows by a numeric column", chart_hint="bar")(t_bottom_n)
register("head", "Preview first rows", produces_chart=False)(t_head)
register("describe", "Descriptive statistics")(t_describe)
register("value_counts", "Frequency counts of a categorical column", chart_hint="bar")(t_value_counts)
register("correlation", "Pearson correlation between columns", chart_hint="scatter")(t_correlation)
register("pivot", "Pivot table")(t_pivot)
register("growth", "Period-over-period growth percentage", chart_hint="line")(t_growth)
register("time_series", "Resample metric over time", chart_hint="line")(t_time_series)
register("rolling", "Rolling average of a column", chart_hint="line")(t_rolling)
register("compare", "Compare metric across groups", chart_hint="bar")(t_compare)
register("kpi_margin", "Profit and profit-margin KPI", chart_hint="bar")(t_kpi_margin)
register("insights", "Summary statistics facts", produces_chart=False)(t_insights)
register("mode", "Most frequent value of a column", chart_hint="bar")(t_mode)
register("yoy", "Year-over-year growth comparison", chart_hint="bar")(t_yoy)
register("outliers", "IQR-based outlier detection", chart_hint="scatter")(t_outliers)


def execute_tool(name: str, df: pd.DataFrame, params: Dict[str, Any]) -> Any:
    """Execute a registered tool by name, returning a result object."""
    spec = REGISTRY.get(name)
    if spec is None:
        raise ToolError(f"Unknown tool '{name}'.")
    try:
        result = spec.fn(df, **params)
    except ToolError:
        raise
    except (KeyError, ValueError, ZeroDivisionError) as exc:
        raise ToolError(f"Tool '{name}' failed: {exc}") from exc
    except Exception as exc:
        raise ToolError(f"Tool '{name}' raised unexpected error: {exc}") from exc
    return _to_result(name, spec, result, params)


def _to_result(name: str, spec: ToolSpec, result: Any, params: Dict[str, Any]) -> Dict[str, Any]:
    """Wrap a tool's return value into a standard result envelope.

    Tools may return ``(DataFrame, extras_dict)`` to attach metadata (e.g. a
    computed correlation coefficient) alongside a chartable table.
    """
    extras: Dict[str, Any] = {}
    if isinstance(result, tuple) and len(result) == 2 and isinstance(result[0], pd.DataFrame):
        result, extras = result
    if isinstance(result, pd.DataFrame):
        return {
            "tool": name,
            "type": "table",
            "table": _table(result),
            "dataframe_size": {"rows": int(len(result)), "cols": int(result.shape[1])},
            "produces_chart": spec.produces_chart,
            "chart_hint": spec.chart_hint,
            "extras": extras,
        }
    return {"tool": name, "type": "value", "value": _value(result), "produces_chart": False,
            "extras": extras}


def _pick_metric(df: pd.DataFrame) -> str:
    candidates = similarity.pick_metric(list(df.columns))
    if candidates:
        return candidates
    numeric = df.select_dtypes(include="number").columns.tolist()
    if numeric:
        return numeric[0]
    raise ToolError("No numeric metric column found in dataset.")
