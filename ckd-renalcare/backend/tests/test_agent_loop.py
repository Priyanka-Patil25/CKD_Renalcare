import pytest
from fastapi.testclient import TestClient
from agents import loop, tools
from agents.llm import MockLLM


@pytest.fixture(scope="module")
def client():
    from main import app
    with TestClient(app) as c:
        yield c


def names(out): return [s["tool"] for s in out["steps"]]


def test_patient_with_labs_takes_the_lab_path():
    out = loop.run("DEMO-001", MockLLM())
    assert names(out)[:2] == ["get_patient_summary", "get_care_gaps"]
    assert "run_screening_model" not in names(out)
    assert "G3b A2" in out["final"] and "doctor decides" in out["final"]


def test_patient_without_labs_takes_the_screening_path():
    out = loop.run("DEMO-007", MockLLM())
    assert names(out)[:2] == ["get_patient_summary", "run_screening_model"]
    assert "get_care_gaps" not in names(out)
    assert "Screening model level" in out["final"]


def test_agent_run_is_logged():
    import db
    n0 = db.one("SELECT count(*) AS n FROM agent_runs WHERE agent='briefing_agent'")["n"]
    loop.run("DEMO-003", MockLLM())
    assert db.one("SELECT count(*) AS n FROM agent_runs WHERE agent='briefing_agent'")["n"] == n0 + 1


class Stuck:                      # a broken LLM that asks for the same thing forever
    def next(self, m, s): return {"tool": "get_care_gaps", "args": {"study_id": "DEMO-001"}}


class Confused:                   # asks for a tool that does not exist, then finishes
    def __init__(self): self.n = 0
    def next(self, m, s):
        self.n += 1
        return {"tool": "delete_everything", "args": {}} if self.n == 1 else {"final": "ok"}


def test_guard_against_repeating():
    out = loop.run("DEMO-001", Stuck())
    assert len(out["steps"]) == 1 and "repeated" in out["final"]


def test_unknown_tool_does_not_crash():
    out = loop.run("DEMO-001", Confused())
    assert "unknown tool" in out["steps"][0]["summary"] and out["final"] == "ok"


def test_tools_are_read_only():
    import db
    before = db.one("SELECT (SELECT count(*) FROM observations) o, (SELECT count(*) FROM care_gap_flags) f, (SELECT count(*) FROM notes) n")
    for t in tools.TOOLS.values():
        if t.name != "search_guidelines":
            t.fn("DEMO-001")
    assert before == db.one("SELECT (SELECT count(*) FROM observations) o, (SELECT count(*) FROM care_gap_flags) f, (SELECT count(*) FROM notes) n")


def test_endpoint(client):
    t = client.post("/api/login", json={"username": "dr.morgan", "password": "doctor123"}).json()["token"]
    h = {"Authorization": "Bearer " + t}
    r = client.post("/api/patients/DEMO-004/agent", headers=h).json()
    assert r["trace"] and r["answer"] and r["verification"]["ok"]
    assert client.post("/api/patients/NOPE/agent", headers=h).status_code == 404
    assert client.post("/api/patients/DEMO-004/agent").status_code == 401
