"""Agent 4 - Validation Agent.

Validates the entire agent run: plan integrity, column existence (suggesting
the closest match when a column is missing), empty results, impossible
calculations, division-by-zero, invalid dates and duplicates. Never fabricates
data -- anything it cannot verify is surfaced as an issue.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd

from backend.agents.analysis_agent import AnalysisOutcome
from backend.tools import similarity
from backend.models.schemas import ExecutionPlan, ValidationIssue, ValidationReport

_COLUMN_PARAMS = (
    "column", "group_by", "metric", "metric_col", "time_col", "value_col",
    "revenue_col", "cost_col", "x", "y", "index", "columns", "values",
)


class ValidationAgent:
    """Validates plans, executions and computed data."""

    def empty_report(self) -> ValidationReport:
        """A neutral report used before any computation happens."""
        return ValidationReport(valid=True, issues=[], corrections=[])

    def validate(
        self,
        plan: ExecutionPlan,
        outcome: AnalysisOutcome,
        original_df: pd.DataFrame,
    ) -> ValidationReport:
        issues: List[ValidationIssue] = []
        corrections: List[str] = []

        # 1. Plan column references exist; otherwise suggest closest match.
        corrections.extend(
            self._validate_columns(plan, original_df, issues)
        )

        # 2. Execution failures.
        self._validate_failures(outcome, issues)

        # 3. Empty results / no answer produced.
        self._validate_results(outcome, issues)

        # 4. Dataset-level checks.
        self._validate_dataset(original_df, issues)

        valid = not any(i.severity == "error" for i in issues)
        return ValidationReport(valid=valid, issues=issues, corrections=corrections)

    # ------------------------------------------------------------------ #
    def _validate_columns(
        self,
        plan: ExecutionPlan,
        df: pd.DataFrame,
        issues: List[ValidationIssue],
    ) -> List[str]:
        corrections: List[str] = []
        actual = list(df.columns)
        referenced: List[str] = []
        for step in plan.steps:
            for k, v in step.params.items():
                if k in _COLUMN_PARAMS and isinstance(v, str):
                    referenced.append(v)
        seen = set()
        for col in referenced:
            if col in seen:
                continue
            seen.add(col)
            if col in actual:
                continue
            closest = similarity.closest_column(col, actual)
            if closest:
                corrections.append(f"'{col}' -> '{closest}'")
                issues.append(
                    ValidationIssue(
                        severity="info",
                        code="column_resolved",
                        message=f"Column '{col}' was not found; using closest match '{closest}'.",
                        suggested_fix=f"Rename the request to use '{closest}'.",
                    )
                )
            else:
                issues.append(
                    ValidationIssue(
                        severity="error",
                        code="missing_column",
                        message=f"Column '{col}' does not exist in the dataset.",
                        suggested_fix="Available columns: " + ", ".join(actual[:12]) + (
                            "..." if len(actual) > 12 else ""
                        ),
                    )
                )
        return corrections

    def _validate_failures(self, outcome: AnalysisOutcome, issues: List[ValidationIssue]) -> None:
        for exec_ in outcome.executions:
            if not exec_.success:
                issues.append(
                    ValidationIssue(
                        severity="error",
                        code="execution_failure",
                        message=f"Step {exec_.step.step} ({exec_.step.action}) failed: {exec_.error}",
                        suggested_fix="Check the parameters or dataset columns used in this step.",
                    )
                )

    def _validate_results(self, outcome: AnalysisOutcome, issues: List[ValidationIssue]) -> None:
        if not any(e.success for e in outcome.executions):
            issues.append(
                ValidationIssue(
                    severity="error",
                    code="no_results",
                    message="No computation steps succeeded, so no answer could be produced.",
                    suggested_fix="Try a different question or check dataset columns.",
                )
            )
            return

        # Empty tables
        for exec_ in outcome.executions:
            if not exec_.success or not exec_.result:
                continue
            result = exec_.result
            if result.get("type") == "table":
                if result.get("dataframe_size", {}).get("rows", 1) == 0:
                    issues.append(
                        ValidationIssue(
                            severity="warning",
                            code="empty_result",
                            message=f"Step {exec_.step.step} ({exec_.step.action}) returned an empty result.",
                            suggested_fix="Widen the filter or choose a different metric.",
                        )
                    )

        # Impossible calculations / division by zero guards
        for exec_ in outcome.executions:
            if not exec_.success or not exec_.result:
                continue
            result = exec_.result
            table = result.get("table", {})
            for col in table.get("columns", []):
                if "growth" in col.lower() or "margin" in col.lower() or "%" in col:
                    vals = [r.get(col) for r in table.get("rows", []) if r.get(col) is not None]
                    for v in vals:
                        if isinstance(v, (int, float)) and abs(v) > 1_000_000:
                            issues.append(
                                ValidationIssue(
                                    severity="warning",
                                    code="extreme_value",
                                    message=f"Column '{col}' contains an extreme value ({v:,.0f}%), "
                                            "likely caused by division by zero.",
                                    suggested_fix="Filter out periods with zero baseline.",
                                )
                            )
                            break

        # Invalid dates in answer table
        for exec_ in outcome.executions:
            if not exec_.success or not exec_.result:
                continue
            table = exec_.result.get("table", {})
            for col in table.get("columns", []):
                if "period" in col.lower() or "date" in col.lower() or "time" in col.lower():
                    bad = [
                        r[col] for r in table.get("rows", [])
                        if r.get(col) and not _is_dateish(r[col])
                    ]
                    if bad:
                        issues.append(
                            ValidationIssue(
                                severity="warning",
                                code="invalid_date",
                                message=f"Column '{col}' contains {len(bad)} unparseable date value(s).",
                                suggested_fix="Coerce the date column to a proper datetime format.",
                            )
                        )
                        break

    def _validate_dataset(self, df: pd.DataFrame, issues: List[ValidationIssue]) -> None:
        if df is None or df.empty:
            issues.append(
                ValidationIssue(
                    severity="error",
                    code="no_dataset",
                    message="No dataset is loaded.",
                    suggested_fix="Upload a CSV or Excel file first.",
                )
            )
            return

        missing_total = int(df.isna().sum().sum())
        if missing_total > 0:
            issues.append(
                ValidationIssue(
                    severity="info",
                    code="missing_values",
                    message=f"Dataset contains {missing_total:,} missing value(s).",
                    suggested_fix="Consider imputing or filtering missing rows before analysis.",
                )
            )

        dupes = int(df.duplicated().sum())
        if dupes > 0:
            issues.append(
                ValidationIssue(
                    severity="info",
                    code="duplicate_rows",
                    message=f"Dataset contains {dupes:,} duplicate row(s).",
                    suggested_fix="Use df.drop_duplicates() if duplicates are not expected.",
                )
            )


def _is_dateish(value: Any) -> bool:
    if isinstance(value, (int, float)):
        return False
    if isinstance(value, str):
        try:
            pd.to_datetime(value, format="mixed", errors="raise")
            return True
        except Exception:
            return False
    return True


validation_agent = ValidationAgent()
