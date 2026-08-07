"""Agent pipeline orchestrator.

Wires the six agents into the full Think -> Plan -> Act -> Verify -> Explain
workflow and emits a QueryResult (or signals that clarification is required).
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

import pandas as pd

from backend.agents.analysis_agent import analysis_agent
from backend.agents.insight_agent import insight_agent
from backend.agents.planner import planner
from backend.agents.validation_agent import validation_agent
from backend.agents.visualization_agent import visualization_agent
from backend.models.schemas import (
    ClarificationRequest,
    DatasetProfile,
    QueryResult,
)


def run_analysis(
    question: str,
    df: pd.DataFrame,
    profile: DatasetProfile,
    hints: Optional[Dict[str, Any]] = None,
) -> QueryResult:
    """Execute the full agent pipeline for one question.

    Args:
        question: the user's natural-language question.
        df: the loaded DataFrame.
        profile: the DatasetProfile produced at upload time.
        hints: optional resolution hints from a prior clarification step.

    Returns:
        A QueryResult containing the plan, executed steps, validation,
        supporting tables, charts, answer, insight and confidence.
    """
    started = time.perf_counter()

    # Think & Plan ----------------------------------------------------- #
    plan = planner.plan(question, profile, hints)
    llm_mode = planner.current_mode

    # Ask for clarification instead of guessing.
    if plan.needs_clarification:
        return QueryResult(
            question=question,
            plan=plan,
            validation=validation_agent.empty_report(),
            dataset_profile=profile,
            confidence=0.0,
            text=plan.clarification_message,
            insight="",
            recommendation="",
            execution_time_ms=round((time.perf_counter() - started) * 1000, 1),
            llm_mode=llm_mode,
            created_at=_now(),
        )

    # Act (compute with pandas) ---------------------------------------- #
    outcome = analysis_agent.execute(plan, df)

    # Verify ------------------------------------------------------------ #
    validation = validation_agent.validate(plan, outcome, df)

    # Visualize --------------------------------------------------------- #
    charts = visualization_agent.visualize(outcome, question)

    # Explain ------------------------------------------------------------ #
    payload = insight_agent.generate(question, plan, outcome, validation, llm_mode)

    # Supporting tables -------------------------------------------------- #
    tables: List[Dict] = []
    for exec_ in outcome.executions:
        if exec_.success and exec_.result and exec_.result.get("type") == "table":
            tables.append(
                {
                    "tool": exec_.step.action,
                    "description": exec_.step.description,
                    "table": exec_.result["table"],
                }
            )

    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)

    return QueryResult(
        question=question,
        plan=plan,
        validation=validation,
        dataset_profile=profile,
        tables=tables,
        charts=charts,
        answer=payload["answer"],
        text=payload["text"],
        insight=payload["insight"],
        recommendation=payload["recommendation"],
        structured=payload["structured"],
        confidence=payload["confidence"],
        follow_ups=payload["follow_ups"],
        execution_time_ms=elapsed_ms,
        llm_mode=payload["llm_mode"],
        created_at=_now(),
    )


def build_clarification(
    question: str,
    plan,
    profile: DatasetProfile,
) -> ClarificationRequest:
    """Wrap an ambiguous plan into an API-ready clarification request."""
    return ClarificationRequest(
        question=question,
        message=plan.clarification_message
        or "Your question is ambiguous — please pick the column you meant.",
        options=plan.clarification_options,
    )


def _now() -> str:
    import datetime as _dt

    return _dt.datetime.now(_dt.timezone.utc).isoformat()
