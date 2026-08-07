"""Excel upload + chart JSON validity check."""
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient

from backend.api.routes import _build_samples
from backend.main import app

client = TestClient(app)


def main() -> None:
    df = _build_samples()["sales_data"].head(300)
    buf = io.BytesIO()
    df.to_excel(buf, index=False, sheet_name="sales")
    buf.seek(0)

    resp = client.post(
        "/api/datasets/upload",
        files={"file": ("sales.xlsx", buf.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    print("xlsx upload:", resp.status_code)
    if resp.status_code != 200:
        print(resp.text)
        return
    ds = resp.json()["dataset_id"]

    resp = client.post("/api/analyze", json={"dataset_id": ds, "question": "Show monthly sales trend."})
    r = resp.json()["result"]
    print("analyze:", resp.status_code, "| charts:", len(r["charts"]), "| tables:", len(r["tables"]))
    for c in r["charts"]:
        fig = c["plotly_json"]
        ok = isinstance(fig.get("data"), list) and len(fig["data"]) > 0
        print(f"  chart {c['chart_type']}: data_ok={ok}")

    resp = client.post("/api/analyze", json={"dataset_id": ds, "question": "Show me the total revenue."})
    r = resp.json()["result"]
    print("total:", r["answer"]["label"], r["answer"]["value"], "| insight:", r["insight"][:80])

    resp = client.post("/api/analyze", json={"dataset_id": ds, "question": "What is the profit margin by region?"})
    r = resp.json()["result"]
    print("margin-by-region: steps", len(r["plan"]["steps"]), "| answer:", r["answer"]["label"], r["answer"]["value"])
    print("validation valid:", r["validation"]["valid"], "issues:", [i["code"] for i in r["validation"]["issues"]])

    print("done")


if __name__ == "__main__":
    main()
