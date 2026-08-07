"""FastAPI endpoint smoke test using TestClient."""
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient

from backend.api.routes import _build_samples
from backend.main import app

client = TestClient(app)


def main() -> None:
    print("health:", client.get("/api/health").json())

    samples = _build_samples()
    csv_buf = io.StringIO()
    samples["sales_data"].head(200).to_csv(csv_buf, index=False)

    resp = client.post(
        "/api/datasets/upload",
        files={"file": ("sales_sample.csv", csv_buf.getvalue().encode("utf-8"), "text/csv")},
    )
    print("upload status:", resp.status_code)
    if resp.status_code != 200:
        print(resp.text)
        return
    data = resp.json()
    ds_id = data["dataset_id"]
    profile = data["profile"]
    print(f"uploaded: {profile['rows']} rows, {profile['columns']} cols, "
          f"dates={profile['date_columns']}")

    resp = client.post("/api/analyze", json={
        "dataset_id": ds_id,
        "question": "Which region generated the highest revenue?",
    })
    print("analyze status:", resp.status_code)
    if resp.status_code != 200:
        print(resp.text)
        return
    result = resp.json()["result"]
    print("answer:", result["answer"]["label"], "=", result["answer"]["value"])
    print("charts:", len(result["charts"]), "tables:", len(result["tables"]))
    print("confidence:", result["confidence"], "llm_mode:", result["llm_mode"])

    print("datasets:", len(client.get("/api/datasets").json()))
    print("history:", len(client.get("/api/history").json()))

    # Error path: no dataset
    resp = client.post("/api/analyze", json={"dataset_id": "nope", "question": "hi"})
    print("analyze no-dataset status:", resp.status_code)

    # Missing column path
    resp = client.post("/api/analyze", json={
        "dataset_id": ds_id,
        "question": "which country has the biggest sales",
    })
    if resp.status_code == 200:
        r = resp.json()["result"]
        print("missing-col corrections:", r["validation"]["corrections"])
    else:
        print("missing-col status:", resp.status_code, resp.text[:200])

    print("\nAPI test complete")


if __name__ == "__main__":
    main()
