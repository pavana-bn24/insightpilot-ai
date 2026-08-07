"""Agent 2 - Dataset Intelligence Agent.

Automatically inspects an uploaded dataset and produces a full DatasetProfile:
shape, dtypes, missing values, duplicates, semantic column buckets, possible
business metrics, outlier detection and an overall data-quality score.
Pure pandas -- no LLM involved.
"""
from __future__ import annotations

import datetime as _dt
from typing import Dict, List

import pandas as pd

from backend.models.schemas import (
    BusinessMetric,
    ColumnProfile,
    DatasetProfile,
)
from backend.tools.data_loader import (
    compute_column_stats,
    detect_metrics,
    memory_usage,
    profile_columns,
)


def profile_dataset(df: pd.DataFrame, dataset_id: str, filename: str) -> DatasetProfile:
    """Generate a DatasetProfile for a DataFrame.

    Args:
        df: the cleaned DataFrame.
        dataset_id: stable identifier for this upload.
        filename: original uploaded file name.

    Returns:
        A DatasetProfile consumed by the frontend Dataset Explorer.
    """
    profiles, buckets = profile_columns(df)

    # Outlier detection (IQR) per numeric column, folded into the profile.
    for p in profiles:
        if p["category"] == "numeric":
            col = p["name"]
            numeric = pd.to_numeric(df[col], errors="coerce")
            q1, q3 = numeric.quantile(0.25), numeric.quantile(0.75)
            iqr = q3 - q1
            if pd.notna(iqr) and iqr > 0:
                lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
                outliers = numeric.between(lower, upper, inclusive="neither").sum()
                p["outliers"] = int(outliers)
                p["outlier_lower"] = _round2(lower)
                p["outlier_upper"] = _round2(upper)

    col_profiles = [ColumnProfile(**p) for p in profiles]

    # Missing values / duplicates
    missing_total = int(df.isna().sum().sum())
    duplicate_rows = int(df.duplicated().sum())

    # Possible metrics + typed business metrics
    possible_metrics = detect_metrics(profiles)
    business_metrics = detect_business_metrics(profiles)

    # Overall data quality score (0-100)
    quality_score = _quality_score(
        missing_total=missing_total,
        duplicate_rows=duplicate_rows,
        total_cells=int(df.size),
    )

    head: List[dict] = []
    for _, row in df.head(10).iterrows():
        head.append({str(c): _json_safe(row[c]) for c in df.columns})

    return DatasetProfile(
        dataset_id=dataset_id,
        filename=filename,
        rows=int(len(df)),
        columns=int(df.shape[1]),
        memory_usage=memory_usage(df),
        missing_total=missing_total,
        duplicate_rows=duplicate_rows,
        numeric_columns=buckets.get("numeric", []),
        categorical_columns=buckets.get("categorical", []),
        date_columns=buckets.get("datetime", []),
        id_columns=buckets.get("id", []),
        possible_metrics=possible_metrics,
        business_metrics=business_metrics,
        quality_score=quality_score,
        column_profiles=col_profiles,
        head=head,
        sample_columns=list(df.columns)[:12],
    )


# --------------------------------------------------------------------------- #
# Business metric detection
# --------------------------------------------------------------------------- #
def detect_business_metrics(profiles: List[Dict]) -> List[BusinessMetric]:
    """Tag numeric columns that look like KPI-style business metrics."""
    metrics: List[BusinessMetric] = []
    for p in profiles:
        if p["category"] != "numeric":
            continue
        name = str(p["name"]).lower()
        if any(k in name for k in ("revenue", "sales", "gmv", "income")):
            metrics.append(BusinessMetric(column=p["name"], label="Revenue", kind="revenue", aggregate="sum"))
        elif any(k in name for k in ("profit", "income")):
            metrics.append(BusinessMetric(column=p["name"], label="Profit", kind="profit", aggregate="sum"))
        elif any(k in name for k in ("margin", "margin%")):
            metrics.append(BusinessMetric(column=p["name"], label="Margin", kind="margin", aggregate="mean"))
        elif any(k in name for k in ("growth", "growth_%", "%")):
            metrics.append(BusinessMetric(column=p["name"], label="Growth", kind="growth", aggregate="mean"))
    return metrics


def _quality_score(missing_total: int, duplicate_rows: int, total_cells: int) -> float:
    """0-100 heuristic data-quality score."""
    if total_cells == 0:
        return 0.0
    missing_penalty = missing_total / total_cells
    dup_penalty = min(duplicate_rows / 1000, 0.2)
    return round(max(0.0, min(100.0, (1 - missing_penalty) * 100 - dup_penalty * 20)), 1)


def _round2(v) -> float:
    try:
        return round(float(v), 2)
    except (TypeError, ValueError):
        return 0.0


def _json_safe(v):
    if pd.isna(v):
        return None
    if isinstance(v, (_dt.datetime, _dt.date, pd.Timestamp)):
        return v.isoformat()
    if hasattr(v, "item"):
        try:
            return v.item()
        except Exception:
            return v
    return v
