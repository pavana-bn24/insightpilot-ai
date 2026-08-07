"""Dataset loading & normalization utilities.

Reads CSV / Excel files into DataFrames, applies light cleaning, and detects
the semantic category of each column (numeric / categorical / datetime / ...).
"""
from __future__ import annotations

import datetime as _dt
import os
import re
from typing import Any, Dict, List, Tuple

import pandas as pd


class DataLoadError(Exception):
    """Raised when a dataset cannot be loaded or parsed."""


DATE_PATTERNS: List[str] = [
    "%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%d/%m/%Y", "%d-%m-%Y",
    "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%m-%d-%Y", "%B %Y",
]

_NUMERIC_HINT = re.compile(
    r"(revenue|profit|sales|amount|qty|quantity|price|cost|margin|"
    r"discount|score|rate|count|sum|value|growth|income|expense|units|"
    r"rating|%|pct|sales|gmv|aov|units|volume|tax|spend|salary)", re.IGNORECASE
)


def _detect_date(series: pd.Series) -> bool:
    """Heuristically detect if a series is a date column."""
    if _is_string_dtype(series.dtype):
        sample = series.dropna().astype(str).head(50)
        if sample.empty:
            return False
        parsed = pd.to_datetime(sample, format="mixed", errors="coerce")
        return parsed.notna().mean() >= 0.9
    return False


def _is_id_column(name: str, values: pd.Series) -> bool:
    lowered = name.lower()
    if any(k in lowered for k in ("id", "key", "code", "sku", "number", "index")):
        if values.nunique() / max(len(values), 1) > 0.95:
            return True
    return False


def _is_string_dtype(dtype) -> bool:
    """True for object dtype and pandas' dedicated string dtype."""
    return dtype == object or isinstance(dtype, pd.StringDtype)


def _classify(name: str, dtype: str, series: pd.Series) -> str:
    """Classify a column into a semantic bucket used by the planner."""
    if _is_id_column(name, series):
        return "id"
    if pd.api.types.is_datetime64_any_dtype(series.dtype):
        return "datetime"
    if pd.api.types.is_bool_dtype(series.dtype):
        return "boolean"
    if pd.api.types.is_numeric_dtype(series.dtype):
        return "numeric"
    if _is_string_dtype(series.dtype):
        nunique = series.nunique(dropna=True)
        if nunique <= 40:
            return "categorical"
        if _detect_date(series):
            return "datetime"
        # Numeric-looking strings that pandas read as text
        coerced = pd.to_numeric(series.dropna(), errors="coerce")
        if len(coerced) > 0 and coerced.notna().mean() > 0.95:
            return "numeric"
        return "text"
    return "other"


def load_dataset(path: str) -> pd.DataFrame:
    """Load a CSV or Excel file into a cleaned DataFrame.

    Args:
        path: Absolute path to the file.

    Returns:
        A cleaned DataFrame with parsed dates.

    Raises:
        DataLoadError: if the file cannot be read or is empty.
    """
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext in (".csv", ".txt"):
            df = pd.read_csv(path, low_memory=False)
        elif ext in (".xlsx", ".xls"):
            df = pd.read_excel(path)
        else:
            raise DataLoadError(f"Unsupported file type: {ext or 'unknown'}")
    except DataLoadError:
        raise
    except Exception as exc:  # pandas/numpy parse errors
        raise DataLoadError(f"Failed to parse dataset: {exc}") from exc

    if df.empty:
        raise DataLoadError("The dataset is empty.")

    # Normalise
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    df = df.loc[:, ~df.columns.duplicated()]
    df = _parse_dates(df)
    return df


def _parse_dates(df: pd.DataFrame) -> pd.DataFrame:
    """Convert string columns that look like dates into datetime columns."""
    for col in df.columns:
        if _is_string_dtype(df[col].dtype):
            sample = df[col].dropna().astype(str).head(50)
            if sample.empty:
                continue
            if _detect_date(df[col]):
                try:
                    df[col] = pd.to_datetime(df[col], format="mixed", errors="coerce")
                except Exception:
                    pass
    return df


def compute_column_stats(df: pd.DataFrame, col: str) -> Dict[str, Any]:
    """Compute a compact statistical profile for one column."""
    series = df[col]
    stats: Dict[str, Any] = {"name": col, "dtype": str(series.dtype)}
    stats["nullable"] = bool(series.isna().any())
    stats["unique"] = int(series.nunique(dropna=True)) if len(series) else 0
    stats["missing"] = int(series.isna().sum())
    stats["missing_pct"] = round(float(series.isna().mean() * 100), 2) if len(series) else 0.0
    stats["category"] = _classify(col, str(series.dtype), series)

    if pd.api.types.is_numeric_dtype(series):
        desc = series.describe()
        stats["min"] = _sanitize(desc.get("min"))
        stats["max"] = _sanitize(desc.get("max"))
        stats["mean"] = _sanitize(desc.get("mean"))
        stats["median"] = _sanitize(series.median())
        stats["std"] = _sanitize(desc.get("std"))
    elif stats["category"] == "datetime":
        stats["min"] = series.min().isoformat() if pd.notna(series.min()) else None
        stats["max"] = series.max().isoformat() if pd.notna(series.max()) else None
    elif pd.api.types.is_object_dtype(series):
        try:
            vc = series.value_counts(dropna=True)
            if not vc.empty:
                stats["top"] = _sanitize(vc.index[0])
                stats["top_freq"] = int(vc.iloc[0])
        except Exception:
            pass
    return stats


def _sanitize(value: Any) -> Any:
    """Convert numpy scalars to JSON-safe Python primitives."""
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            return value
    if isinstance(value, (_dt.datetime, _dt.date)):
        return value.isoformat()
    return value


def profile_columns(df: pd.DataFrame) -> Tuple[List[Dict[str, Any]], Dict[str, List[str]]]:
    """Profile every column and bucket them into semantic groups."""
    profiles: List[Dict[str, Any]] = []
    buckets: Dict[str, List[str]] = {
        "numeric": [], "categorical": [], "datetime": [],
        "text": [], "id": [], "boolean": [],
    }
    for col in df.columns:
        stats = compute_column_stats(df, col)
        profiles.append(stats)
        cat = stats["category"]
        if cat in buckets:
            buckets[cat].append(col)
    return profiles, buckets


def detect_metrics(profiles: List[Dict[str, Any]]) -> List[str]:
    """Heuristically flag columns that are likely business metrics."""
    metrics: List[str] = []
    for p in profiles:
        if p["category"] != "numeric":
            continue
        if _NUMERIC_HINT.search(p["name"]) or p["missing_pct"] == 0:
            metrics.append(p["name"])
    return metrics


def memory_usage(df: pd.DataFrame) -> str:
    """Human-readable memory usage of the dataframe."""
    total = df.memory_usage(deep=True).sum()
    for unit in ("B", "KB", "MB", "GB"):
        if total < 1024:
            return f"{total:.1f} {unit}"
        total /= 1024
    return f"{total:.1f} TB"
