"""HTTP routes for InsightPilot AI.

Separated from the app factory so the API can be tested and mounted cleanly.
"""
from __future__ import annotations

import os
import shutil
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, HTTPException, UploadFile

from backend.agents.dataset_agent import profile_dataset
from backend.models.schemas import AnalyzeRequest, AnalyzeResponse
from backend.pipeline import build_clarification, run_analysis
from backend.tools.data_loader import DataLoadError, load_dataset
from backend.utils.llm.factory import provider_status

router = APIRouter(prefix="/api")

# --------------------------------------------------------------------------- #
# In-memory store (adequate for a demo; documented tradeoff).
# --------------------------------------------------------------------------- #
_datasets: Dict[str, Dict] = {}
_history: List[Dict] = []
BASE_DIR = Path(__file__).resolve().parents[2]
UPLOAD_DIR = BASE_DIR / "data" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _list_sample_datasets() -> List[Path]:
    samples_dir = BASE_DIR / "data" / "samples"
    return sorted(samples_dir.glob("*.csv")) if samples_dir.exists() else []


def _resolve_dataset(dataset_id: str) -> Optional[Dict]:
    """Resolve an uploaded or bundled sample dataset (lazy-loading samples)."""
    if dataset_id in _datasets:
        return _datasets[dataset_id]
    if dataset_id.startswith("sample:"):
        stem = dataset_id.split(":", 1)[1]
        sample = BASE_DIR / "data" / "samples" / f"{stem}.csv"
        if sample.exists():
            df = load_dataset(str(sample))
            profile = profile_dataset(df, dataset_id, sample.name)
            entry = {"df": df, "profile": profile, "path": str(sample), "ts": time.time()}
            _datasets[dataset_id] = entry
            return entry
    return None


# --------------------------------------------------------------------------- #
# Health
# --------------------------------------------------------------------------- #
@router.get("/health")
def health() -> Dict:
    return {
        "status": "ok",
        **provider_status(),
        "datasets_loaded": len(_datasets),
    }


# --------------------------------------------------------------------------- #
# Datasets
# --------------------------------------------------------------------------- #
@router.get("/datasets")
def list_datasets() -> List[Dict]:
    out = []
    for ds_id, entry in _datasets.items():
        profile = entry["profile"]
        out.append(
            {
                "id": ds_id,
                "filename": profile.filename,
                "rows": profile.rows,
                "columns": profile.columns,
                "uploaded_at": entry["ts"],
                "has_date": bool(profile.date_columns),
                "metrics": profile.possible_metrics[:6],
                "quality_score": profile.quality_score,
            }
        )
    for sample in _list_sample_datasets():
        if not any(d.get("filename") == sample.name for d in out):
            out.append(
                {
                    "id": f"sample:{sample.stem}",
                    "filename": sample.name,
                    "rows": None,
                    "columns": None,
                    "uploaded_at": None,
                    "sample": True,
                    "has_date": None,
                    "metrics": [],
                    "quality_score": None,
                }
            )
    out.sort(key=lambda d: (d.get("sample", False), d.get("uploaded_at") or ""), reverse=True)
    return out


@router.post("/datasets/upload")
def upload_dataset(file: UploadFile = File(...)) -> Dict:
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in (".csv", ".txt", ".xlsx", ".xls"):
        raise HTTPException(400, "Only CSV and Excel (.xlsx/.xls) files are supported.")

    dataset_id = uuid.uuid4().hex[:12]
    dest = UPLOAD_DIR / f"{dataset_id}{ext}"
    try:
        with dest.open("wb") as fh:
            shutil.copyfileobj(file.file, fh)
        df = load_dataset(str(dest))
        profile = profile_dataset(df, dataset_id, file.filename or dest.name)
        _datasets[dataset_id] = {
            "df": df,
            "profile": profile,
            "path": str(dest),
            "ts": time.time(),
        }
        return {"dataset_id": dataset_id, "profile": profile}
    except DataLoadError as exc:
        dest.unlink(missing_ok=True)
        raise HTTPException(400, str(exc))
    except Exception as exc:
        dest.unlink(missing_ok=True)
        raise HTTPException(500, f"Upload failed: {exc}")


@router.get("/datasets/{dataset_id}")
def get_dataset(dataset_id: str) -> Dict:
    entry = _resolve_dataset(dataset_id)
    if not entry:
        raise HTTPException(404, "Dataset not found. Upload a dataset first.")
    return {"dataset_id": dataset_id, "profile": entry["profile"]}


# --------------------------------------------------------------------------- #
# Analysis
# --------------------------------------------------------------------------- #
@router.post("/analyze", response_model=AnalyzeResponse)
def analyze(req: AnalyzeRequest) -> AnalyzeResponse:
    if not req.question or not req.question.strip():
        raise HTTPException(400, "Question cannot be empty.")
    entry = _resolve_dataset(req.dataset_id)
    if not entry:
        raise HTTPException(400, "No dataset loaded. Upload a CSV/Excel file first.")

    result = run_analysis(req.question.strip(), entry["df"], entry["profile"], req.hints or {})

    # Clarification round-trip: do not record it as an analysis.
    if result.plan.needs_clarification:
        return AnalyzeResponse(
            kind="clarification",
            clarification=build_clarification(req.question, result.plan, entry["profile"]),
        )

    history_id = uuid.uuid4().hex[:12]
    _history.append(
        {
            "id": history_id,
            "dataset_id": req.dataset_id,
            "filename": entry["profile"].filename,
            "question": result.question,
            "confidence": result.confidence,
            "intent": result.plan.intent,
            "llm_mode": result.llm_mode,
            "created_at": result.created_at,
            "answer_label": result.answer.get("label", ""),
            "answer_value": result.answer.get("value", ""),
            "insight": result.insight,
            "recommendation": result.recommendation,
            "structured": result.structured.model_dump(mode="json"),
            "result": result.model_dump(mode="json"),
        }
    )
    if len(_history) > 200:
        _history[:] = _history[-200:]

    return AnalyzeResponse(kind="answer", result=result, history_id=history_id)


# --------------------------------------------------------------------------- #
# Conversation / history
# --------------------------------------------------------------------------- #
@router.get("/history")
def history() -> List[Dict]:
    return list(reversed(_history))


@router.get("/conversation")
def conversation() -> List[Dict]:
    """A conversational view of the analysis history (user -> assistant turns)."""
    turns = []
    for h in reversed(_history):
        turns.append({"role": "user", "content": h["question"], "history_id": h["id"]})
        turns.append(
            {
                "role": "assistant",
                "content": h["insight"] or h["result"].get("text", ""),
                "answer": {"label": h["answer_label"], "value": h["answer_value"]},
                "history_id": h["id"],
            }
        )
    return turns


@router.delete("/history/{history_id}")
def delete_history(history_id: str) -> Dict:
    global _history
    _history = [h for h in _history if h["id"] != history_id]
    return {"deleted": True}


@router.get("/suggestions/{dataset_id}")
def suggestions(dataset_id: str) -> Dict:
    """Context-aware suggested questions built from the dataset profile."""
    entry = _resolve_dataset(dataset_id)
    if not entry:
        raise HTTPException(404, "Dataset not found.")
    profile = entry["profile"]
    metric = (profile.possible_metrics or ["the key metric"])[0]
    dim = (profile.categorical_columns or ["the main category"])[0]
    date = (profile.date_columns or [])[0]

    base = [
        f"Which {dim} generated the highest {metric}?",
        f"Show the trend of {metric} over time.",
        f"What is the average {metric} per {dim}?",
        f"Calculate the profit margin.",
    ]
    if date:
        base.append(f"Which period had the biggest growth in {metric}?")
    if len(profile.numeric_columns) >= 2:
        base.append(
            f"What is the correlation between {profile.numeric_columns[0]} and {profile.numeric_columns[1]}?"
        )
    if len(profile.categorical_columns) >= 2:
        base.append(f"Compare {profile.categorical_columns[0]} and {profile.categorical_columns[1]}.")

    return {"dataset_id": dataset_id, "questions": base[:8]}


# --------------------------------------------------------------------------- #
# Sample seeding (dev convenience)
# --------------------------------------------------------------------------- #
@router.get("/samples/create")
def create_samples() -> Dict:
    created = []
    for name, df in _build_samples().items():
        path = BASE_DIR / "data" / "samples" / f"{name}.csv"
        df.to_csv(path, index=False)
        created.append(name)
    return {"created": created}


def _build_samples() -> Dict[str, Any]:
    """Return example DataFrames used by the dashboard demo."""
    import datetime as _dt

    import numpy as np
    import pandas as pd

    rng = np.random.default_rng(42)

    regions = ["East", "West", "North", "South"]
    categories = ["Electronics", "Furniture", "Clothing", "Groceries"]
    cat_econ = {
        "Electronics": (220.0, 0.62),
        "Furniture": (180.0, 0.68),
        "Clothing": (60.0, 0.58),
        "Groceries": (35.0, 0.72),
    }
    region_weight = {"East": 0.28, "West": 0.32, "North": 0.22, "South": 0.18}
    months = 24
    period_start = _dt.date(2024, 1, 1)

    rows = []
    for m in range(months):
        month_idx = m + 1
        year = period_start.year + (period_start.month - 1 + m) // 12
        month = (period_start.month - 1 + m) % 12 + 1
        month_date = _dt.date(year, month, 1)
        for region, weight in region_weight.items():
            base_orders = 220 * weight
            orders = max(1, int(round(base_orders * (1 + 0.05 * month_idx) * rng.uniform(0.85, 1.15))))
            for _ in range(orders):
                category = rng.choice(categories, p=[0.34, 0.26, 0.22, 0.18])
                unit_price, cost_ratio = cat_econ[category]
                qty = int(rng.integers(1, 6))
                revenue = round(unit_price * qty * rng.lognormal(0, 0.12), 2)
                cost = round(revenue * cost_ratio * rng.uniform(0.9, 1.15), 2)
                day = int(rng.integers(1, 29))
                rows.append({
                    "Order ID": f"ORD-{len(rows) + 1:06d}",
                    "Region": region,
                    "Category": category,
                    "Date": pd.Timestamp(month_date.replace(day=day)),
                    "Revenue": revenue,
                    "Cost": cost,
                    "Discount": round(float(rng.uniform(0, 0.35)), 2),
                    "Units Sold": qty,
                    "Profit": round(revenue - cost, 2),
                })

    sales = pd.DataFrame(rows)

    n2 = 300
    customers = pd.DataFrame(
        {
            "Customer ID": [f"CUS-{i:04d}" for i in range(1, n2 + 1)],
            "Segment": rng.choice(["Premium", "Standard", "Basic"], size=n2, p=[0.25, 0.45, 0.3]),
            "Region": rng.choice(regions, size=n2),
            "Acquisition Date": rng.choice(pd.date_range("2023-01-01", periods=600, freq="D"), size=n2),
            "Lifetime Revenue": np.round(rng.lognormal(mean=6.5, sigma=0.9, size=n2), 2),
            "Orders": rng.integers(1, 40, size=n2),
            "Churn Risk Score": np.round(rng.uniform(0, 100, size=n2), 1),
        }
    )
    return {"sales_data": sales, "customer_data": customers}
