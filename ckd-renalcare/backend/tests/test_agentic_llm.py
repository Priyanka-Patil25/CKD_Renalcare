import json
from types import SimpleNamespace as NS
from fastapi.testclient import TestClient
from agentic.llm import ClaudeBrain, ScriptedBrain, get_brain
from agentic.loop import run_agent
from agentic.verify import verify
from agentic.lab_reader import propose
import db


class FakeClient:
    """Pretends to be the Anthropic client: asks for 2 tools, then answers."""
    def __init__(self, final_text):
        self.calls, self.final = [], final_text
        self.messages = self

    def create(self, **kw):
        self.calls.append(kw)
        n = len(kw["messages"])
        if n == 1:
            return NS(content=[NS(type="tool_use", id="x", name="get_patient_summary", input={})])
        if n == 3:
            return NS(content=[NS(type="tool_use", id="y", name="get_care_gaps", input={})])
        return NS(content=[NS(type="text", text=self.final)])


def test_claude_brain_wiring_with_fake_client():
    fc = FakeClient("Patient has G3b A2 CKD. Please review the open flags carefully.")
    out = run_agent("brief", "DEMO-001", ClaudeBrain(client=fc, model="m"))
    assert out["finished"] and out["brain"] == "claude-llm-brain"
    assert [t["tool"] for t in out["trace"] if t["kind"] == "tool"] == ["get_patient_summary", "get_care_gaps"]
    assert fc.calls[0]["tools"] and "SUGGEST" in fc.calls[0]["system"]
    assert fc.calls[-1]["messages"][-1]["content"][0]["type"] == "tool_result"


def test_get_brain_falls_back_without_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert isinstance(get_brain(), ScriptedBrain)


def test_scripted_answer_passes_verifier_and_cites_pages():
    out = run_agent("brief", "DEMO-001", ScriptedBrain())
    assert out["verification"]["ok"], out["verification"]


def test_verifier_catches_invented_number_citation_and_action_claim():
    hist = [{"tool": "get_patient_summary", "args": {}, "result": {"egfr": 41.0}},
            {"tool": "search_guidelines", "args": {}, "result": {"passages": [{"doc": "KDIGO 2024 CKD", "page": "S197", "text": "x"}]}}]
    assert verify("eGFR is 41.0 [KDIGO 2024 CKD S197] so review monitoring.", hist)["ok"]
    assert not verify("eGFR is 55 so review monitoring soon, please.", hist)["ok"]                 # invented number
    assert not verify("eGFR is 41.0 [KDIGO 2099 Made Up S1] so review it.", hist)["ok"]            # fake citation
    assert not verify("eGFR is 41.0. I have updated the prescription for you.", hist)["ok"]        # claims an action


def test_lab_reader_proposes_but_saves_nothing():
    before = db.one("SELECT count(*) AS n FROM observations")["n"]
    r = propose("Date: 2026-03-12\nCreatinine: 1.9 mg/dL\nUACR >300\nHbA1c 72")
    d = {p["code"]: p for p in r["proposed"]}
    assert d["creatinine"]["value"] == 1.9 and d["uacr"]["value"] is None and d["uacr"]["warning"]
    assert d["hba1c"]["warning"]                                                  # 72 is not a believable HbA1c
    assert db.one("SELECT count(*) AS n FROM observations")["n"] == before


def test_endpoints_need_doctor_and_work():
    import main
    c = TestClient(main.app)
    assert c.post("/api/patients/DEMO-001/agent").status_code in (401, 403)
    tok = c.post("/api/login", json={"username": "dr.morgan", "password": "doctor123"}).json()["token"]
    h = {"Authorization": f"Bearer {tok}"}
    r = c.post("/api/patients/DEMO-001/agent", headers=h).json()
    assert r["finished"] and "verification" in r
    r = c.post("/api/patients/DEMO-001/labs/propose", headers=h, json={"text": "eGFR 38"}).json()
    assert r["proposed"][0]["code"] == "egfr"
    tok2 = c.post("/api/login", json={"username": "reception1", "password": "reception123"}).json()["token"]
    assert c.post("/api/patients/DEMO-001/labs/propose", headers={"Authorization": f"Bearer {tok2}"}, json={"text": "eGFR 38"}).status_code == 403


def test_open_source_brain_wiring_with_fake_server():
    from agentic.llm import OpenAICompatBrain
    seen = []

    def fake_post(path, body):
        seen.append(body)
        n = len(body["messages"])
        if n == 2:
            return {"choices": [{"message": {"tool_calls": [{"function": {"name": "get_patient_summary", "arguments": "{}"}}]}}]}
        return {"choices": [{"message": {"content": "eGFR is 40.0 [KDIGO 2024 CKD S197]. Please review the open flags."}}]}
    out = run_agent("brief", "DEMO-001", OpenAICompatBrain(post=fake_post))
    assert out["finished"] and out["brain"] == "open-source-llm-brain"
    assert seen[0]["tools"][0]["function"]["name"] and seen[1]["messages"][-1]["role"] == "tool"


def test_get_brain_picks_open_source(monkeypatch):
    from agentic.llm import OpenAICompatBrain
    monkeypatch.setenv("CKD_LLM", "ollama")
    assert isinstance(get_brain(), OpenAICompatBrain)
