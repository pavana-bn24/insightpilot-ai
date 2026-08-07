"""Quick end-to-end smoke test of the InsightPilot pipeline."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.api.routes import _build_samples
from backend.agents.dataset_agent import profile_dataset
from backend.pipeline import run_analysis


def main() -> None:
    samples = _build_samples()
    df = samples["sales_data"]
    print(f"Sales data: {df.shape}")
    profile = profile_dataset(df, "test", "sales_data.csv")
    print(f"Profile: rows={profile.rows} cols={profile.columns} dupes={profile.duplicate_rows}")
    print(f"  numeric={profile.numeric_columns}")
    print(f"  categorical={profile.categorical_columns}")
    print(f"  date={profile.date_columns}")
    print(f"  metrics={profile.possible_metrics}")

    questions = [
        "Which region generated the highest revenue?",
        "Show monthly sales trend.",
        "Which product category performed best?",
        "Compare East and West regions by profit.",
        "Calculate profit margin.",
        "What is the correlation between discount and profit?",
        "Which month had the biggest growth?",
        "What is the average revenue per region?",
        "Top 5 customers by lifetime revenue?",
    ]

    failures = 0
    for q in questions:
        try:
            result = run_analysis(q, df, profile)
            steps_done = sum(1 for s in result.plan.steps if s.status == "completed")
            step_str = f"{steps_done}/{len(result.plan.steps)}"
            tables = len(result.tables)
            charts = len(result.charts)
            answer = result.answer
            print(f"\nQ: {q}")
            print(f"  intent={result.plan.intent} steps={step_str} tables={tables} charts={charts} conf={result.confidence}")
            print(f"  answer: {answer.get('label')} = {answer.get('value')} ({answer.get('detail')})")
            print(f"  insight: {result.insight[:120]}")
            for issue in result.validation.issues:
                if issue.severity == "error":
                    print(f"  ERROR: {issue.message}")
        except Exception as exc:
            failures += 1
            print(f"\nQ: {q}\n  FAILED: {type(exc).__name__}: {exc}")

    print(f"\n=== {len(questions) - failures}/{len(questions)} passed ===")
    if failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
