"""Agent 3 - Analysis Agent.

Executes an ExecutionPlan against the dataset using ONLY the registered pandas
tools. It tracks each step's outcome, keeps the working DataFrame for chained
steps, and marks the last chartable table as the answer source for downstream
agents. The LLM never computes anything -- this agent is the sole arithmetic
executor.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import pandas as pd

from backend.tools import pandas_tools
from backend.tools.pandas_tools import ToolError
from backend.models.schemas import ExecutionPlan, PlanStep, ValidationIssue, ValidationReport


@dataclass
class StepExecution:
    """Outcome of executing a single plan step."""

    step: PlanStep
    success: bool
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    dataframe: Optional[pd.DataFrame] = None


@dataclass
class AnalysisOutcome:
    """Full result of executing a plan."""

    plan: ExecutionPlan
    executions: List[StepExecution] = field(default_factory=list)
    answer_table: Optional[Dict[str, Any]] = None
    answer_tool: Optional[str] = None
    working_df: Optional[pd.DataFrame] = None
    computed_facts: Dict[str, Any] = field(default_factory=dict)


# Tools that only supplement an answer (never the answer themselves).
_SUPPLEMENTARY_TOOLS = {"insights", "head", "filter"}


class AnalysisAgent:
    """Executes execution plans with pandas."""

    def execute(self, plan: ExecutionPlan, df: pd.DataFrame) -> AnalysisOutcome:
        outcome = AnalysisOutcome(plan=plan, working_df=df.copy())
        working = df.copy()

        for step in plan.steps:
            step.status = "running"
            spec = pandas_tools.REGISTRY.get(step.action)
            if spec is None:
                step.status = "failed"
                outcome.executions.append(
                    StepExecution(step=step, success=False, error=f"Unknown tool '{step.action}'")
                )
                continue

            try:
                result = pandas_tools.execute_tool(step.action, working, step.params)
                step.status = "completed"
                step.result = result

                # Chain dataframes for subsequent steps when applicable.
                if isinstance(result, dict) and result.get("type") == "table":
                    table = result.get("table", {})
                    df_from_table = _df_from_table(table)
                    if df_from_table is not None and not df_from_table.empty:
                        working = df_from_table

                execution = StepExecution(step=step, success=True, result=result,
                                          dataframe=working.copy())
                outcome.executions.append(execution)

                # Track the answer source: the last *primary* chartable table.
                if isinstance(result, dict) and result.get("type") == "table":
                    if step.action not in _SUPPLEMENTARY_TOOLS:
                        outcome.answer_table = result.get("table")
                        outcome.answer_tool = step.action
                    elif outcome.answer_table is None:
                        outcome.answer_table = result.get("table")
                        outcome.answer_tool = step.action

            except ToolError as exc:
                step.status = "failed"
                step.note = str(exc)
                outcome.executions.append(StepExecution(step=step, success=False, error=str(exc)))
                continue
            except Exception as exc:  # never let a step crash the whole run
                step.status = "failed"
                step.note = f"Execution error: {exc}"
                outcome.executions.append(StepExecution(step=step, success=False, error=str(exc)))
                continue

        # Compute compact facts from the working dataframe for the Insight Agent.
        outcome.computed_facts = self._build_facts(plan, outcome)
        return outcome

    # ------------------------------------------------------------------ #
    def _build_facts(self, plan: ExecutionPlan, outcome: AnalysisOutcome) -> Dict[str, Any]:
        """Extract answer-oriented facts (top row, key numbers) from results."""
        facts: Dict[str, Any] = {}
        for exec_ in outcome.executions:
            if not exec_.success or not exec_.result:
                continue
            result = exec_.result
            if result.get("type") == "table":
                table = result["table"]
                rows = table.get("rows", [])
                if rows:
                    facts[f"{exec_.step.action}_first_row"] = rows[0]
                    facts[f"{exec_.step.action}_row_count"] = table.get("row_count", 0)
            elif result.get("type") == "value":
                facts[f"{exec_.step.action}_value"] = result.get("value")
        return facts

    # ------------------------------------------------------------------ #
    def validate_execution(self, outcome: AnalysisOutcome) -> ValidationReport:
        """Quick structural check; full validation lives in the Validation Agent."""
        issues: List[ValidationIssue] = []
        failed = [e for e in outcome.executions if not e.success]
        valid = len(failed) == 0
        if not valid:
            issues.append(
                ValidationIssue(
                    severity="error",
                    code="step_failure",
                    message="; ".join(e.error or "unknown" for e in failed),
                    suggested_fix="Adjust the plan or dataset columns.",
                )
            )
        return ValidationReport(valid=valid, issues=issues)


def _df_from_table(table: Dict[str, Any]) -> Optional[pd.DataFrame]:
    """Rebuild a DataFrame from a JSON table (used for step chaining)."""
    cols = table.get("columns", [])
    rows = table.get("rows", [])
    if not cols or not rows:
        return None
    try:
        return pd.DataFrame(rows, columns=cols)
    except Exception:
        return None


analysis_agent = AnalysisAgent()
