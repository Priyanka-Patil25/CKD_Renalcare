"""Four-agent pipeline: order, names, role block, and 'no evidence means no advice'."""
import orchestrator
from fastapi.testclient import TestClient
import main

NAMES = ["Clinical Data Agent", "Risk Assessment Agent", "Clinical Management Agent", "Diet Recommendation Agent"]


def _login(c, u, p):
    return {"Authorization": "Bearer " + c.post("/api/login", json={"username": u, "password": p}).json()["token"]}


def test_agents_run_in_project_order():
    r = orchestrator.run("DEMO-001")
    assert [a["name"] for a in r["agents"]] == NAMES
    assert all(a["review_required"] for a in r["agents"])
    assert "Decision support only" in r["disclaimer"]


def test_no_guideline_text_means_insufficient_evidence_not_invented_advice(monkeypatch):
    monkeypatch.setattr(orchestrator, "retrieve", lambda q, k=4: [])
    r = orchestrator.run("DEMO-001")
    mg, dt = r["agents"][2], r["agents"][3]
    assert all(not g["evidence"] for g in mg["topics"] + dt["topics"])
    assert dt["status"] == "insufficient_evidence" and r["citations"] == []


def test_one_failing_agent_does_not_hide_the_others(monkeypatch):
    monkeypatch.setattr(orchestrator, "diet", lambda p, risk: 1 / 0)
    r = orchestrator.run("DEMO-001")
    assert r["agents"][3]["status"] == "failed" and r["agents"][0]["status"] == "completed"


def test_only_doctor_can_run_and_clients_get_the_report():
    c = TestClient(main.app)
    assert c.post("/api/patients/DEMO-001/pipeline", headers=_login(c, "reception1", "reception123")).status_code == 403
    d = _login(c, "dr.morgan", "doctor123")
    assert len(c.post("/api/patients/DEMO-001/pipeline", headers=d).json()["agents"]) == 4
    assert c.get("/api/patients/DEMO-001/pipeline", headers=d).json()["generated_at"]
    assert c.post("/api/patients/NOPE-1/pipeline", headers=d).status_code == 404
