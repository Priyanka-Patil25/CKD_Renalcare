from datetime import date
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    from main import app
    with TestClient(app) as c:
        yield c


def tok(client, u, p):
    r = client.post("/api/login", json={"username": u, "password": p})
    return {"Authorization": "Bearer " + r.json()["token"]}


def test_reception_flow(client):
    h = tok(client, "reception1", "reception123")
    reg = client.post("/api/patients", json={"name": "Test Intake", "age": 55, "sex": "F", "reason": "Check"}, headers=h).json()
    pid, today = reg["id"], date.today().isoformat()
    body = {"visit_date": today, "visit_id": reg["visit_id"], "reason": "Check", "values": {"sbp": 150, "dbp": 90, "creatinine": 1.6, "uacr": 80},
            "conditions": {"diabetes": True, "hypertension": True}, "medicines": ["Metformin", "Telmisartan"], "notes": "Fasting", "source": "manual"}
    r = client.post(f"/api/patients/{pid}/clinical-entry", json=body, headers=h)
    assert r.status_code == 200 and r.json()["saved"] and r.json()["visit_id"] == reg["visit_id"]
    r2 = client.post(f"/api/patients/{pid}/clinical-entry", json=body, headers=h).json()
    assert r2["observations"]["added"] == 0 and r2["observations"]["duplicates_ignored"] >= 4
    d = client.get(f"/api/patients/{pid}/intake", headers=h).json()
    v = d["visits"][0]
    assert d["diabetes"] and v["status"].startswith("Draft") and {o["key"] for o in v["observations"]} >= {"sbp", "egfr", "uacr"}
    assert [m["name"] for m in v["medicines"]] == ["Metformin", "Telmisartan"] and v["notes"][0]["body"] == "Fasting"
    s = client.post(f"/api/patients/{pid}/visits/{v['visit_id']}/submit-review", headers=h).json()
    assert s["submitted"] and s["status"] == "Submitted for doctor review"
    assert client.get(f"/api/patients/{pid}/intake", headers=h).json()["visits"][0]["status"] == "Submitted for doctor review"
    assert client.get("/api/patients/NOPE/intake", headers=h).status_code == 404
    assert client.get(f"/api/patients/{pid}/intake").status_code == 401
