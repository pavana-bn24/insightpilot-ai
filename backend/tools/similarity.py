"""Column name similarity utilities.

Used by the Validation Agent to suggest the closest matching column when a
user request references a column that does not exist, and by the Analysis
Agent to pick sensible metric columns for open-ended questions.
"""
from __future__ import annotations

import difflib
import re
from typing import List, Optional

_METRIC_KEYWORDS = [
    "revenue", "profit", "sales", "amount", "price", "cost", "margin",
    "discount", "quantity", "qty", "units", "count", "score", "rating",
    "income", "expense", "value", "total", "spend", "gmv", "aov", "tax",
]

_NEGATIVE_METRIC_KEYWORDS = ["profit_margin", "margin_%", "growth_%", "growth"]


def normalize(name: str) -> str:
    """Normalise a column name for fuzzy matching."""
    text = str(name).strip().lower()
    text = re.sub(r"[_\-\s/]+", " ", text)
    text = re.sub(r"[^a-z0-9%]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def tokenize(name: str) -> List[str]:
    return [t for t in normalize(name).split() if t]


def similarity_score(a: str, b: str) -> float:
    """Return a 0..1 similarity between two column names."""
    na, nb = normalize(a), normalize(b)
    if na == nb:
        return 1.0
    ratio = difflib.SequenceMatcher(None, na, nb).ratio()
    ta, tb = set(tokenize(a)), set(tokenize(b))
    jaccard = len(ta & tb) / len(ta | tb) if (ta | tb) else 0.0
    overlap = len(ta & tb) / max(len(ta), len(tb), 1)
    return max(ratio, 0.6 * jaccard + 0.4 * overlap)


def closest_column(requested: str, available: List[str], threshold: float = 0.35) -> Optional[str]:
    """Find the best matching column for a requested name.

    Args:
        requested: name the user/LLM referenced (may be fuzzy).
        available: actual columns in the DataFrame.
        threshold: minimum score to accept a match.

    Returns:
        The best column name, or None if nothing matches well enough.
    """
    if not available:
        return None
    if requested in available:
        return requested
    scored = sorted(
        ((similarity_score(requested, c), c) for c in available),
        key=lambda x: x[0],
        reverse=True,
    )
    best_score, best = scored[0]
    if best_score >= threshold:
        return best
    return None


def pick_metric(columns: List[str]) -> Optional[str]:
    """Pick the most likely business metric from a list of column names.

    Uses whole-token matching (not substring) so that e.g. "count" does not
    accidentally match "discount", and multi-word keywords split on '_'.
    """
    scored: List[tuple] = []
    for col in columns:
        tokens = set(tokenize(col))
        score = 0.0
        for kw in _METRIC_KEYWORDS:
            kw_parts = set(re.split(r"[\s_/]+", kw))
            if kw_parts.issubset(tokens):
                score += 1.0
        for kw in _NEGATIVE_METRIC_KEYWORDS:
            kw_parts = set(re.split(r"[\s_/]+", kw))
            if kw_parts.issubset(tokens):
                score -= 0.5
        if re.search(r"%", col):
            score += 0.3
        scored.append((score, col))
    if not scored:
        return None
    scored.sort(key=lambda x: x[0], reverse=True)
    if scored[0][0] > 0:
        return scored[0][1]
    return None


def is_dimensional(column: str) -> bool:
    """True if a column looks like a dimension/grouping column."""
    text = normalize(column)
    if any(k in text for k in ("revenue", "profit", "sales", "amount", "price", "cost", "margin", "qty", "quantity", "discount")):
        return False
    return True
