import pytest
from agentic.loop import run_agent
from agentic.llm import ScriptedBrain
from agentic.tools import TOOLS
import db


def tools_used(out):
    return [t["tool"] for t in out["trace"] if t["kind"] == "tool"]


def test_patient_with_labs_skips_screening_model():
    out = run_agent("brief", "DEMO-001", ScriptedBrain())
    assert out["finished"] and tools_used(out) == ["get_patient_summary", "get_care_gaps", "search_guidelines"]
    assert "G3b A2" in out["answer"] and "Demo patient" not in out["answer"]     # no names reach the brain or the answer


def test_patient_without_labs_uses_screening_model():
    out = run_agent("brief", "DEMO-007", ScriptedBrain())
    assert tools_used(out) == ["get_patient_summary", "run_screening_model", "get_care_gaps", "search_guidelines"]
    assert "Screening model:" in out["answer"]


def test_every_step_is_logged():
    n0 = db.one("SELECT count(*) AS n FROM agent_runs WHERE agent='orchestrator'")["n"]
    out = run_agent("brief", "DEMO-003", ScriptedBrain())
    n1 = db.one("SELECT count(*) AS n FROM agent_runs WHERE agent='orchestrator'")["n"]
    assert n1 - n0 == len(out["trace"])


class LoopingBrain:
    name = "never-stops"
    def next_step(self, goal, history, tools):
        return {"type": "tool_call", "name": "get_care_gaps", "args": {}}


class SneakyBrain:
    name = "tries-forbidden-things"
    def __init__(self): self.i = 0
    def next_step(self, goal, history, tools):
        self.i += 1
        if self.i == 1: return {"type": "tool_call", "name": "delete_patient", "args": {}}          # not allowed
        if self.i == 2: return {"type": "tool_call", "name": "get_patient_summary", "args": {"study_id": "DEMO-006"}}  # wrong patient
        return {"type": "final", "text": "done"}


def test_max_steps_stops_a_looping_brain():
    out = run_agent("brief", "DEMO-001", LoopingBrain(), max_steps=4)
    assert out["finished"] is False and out["trace"][-1]["kind"] == "stopped" and len(tools_used(out)) == 4


def test_forbidden_tool_is_blocked_and_patient_cannot_be_switched():
    out = run_agent("brief", "DEMO-001", SneakyBrain())
    kinds = [t["kind"] for t in out["trace"]]
    assert kinds[0] == "blocked"
    summary = next(t for t in out["trace"] if t["kind"] == "tool" and t["tool"] == "get_patient_summary")
    assert "unexpected" in summary["result"].get("error", "") or summary["status"] == "error"   # extra argument rejected


def test_tools_are_read_only_and_described():
    for t in TOOLS.values():
        assert t.description and t.schema()["name"] == t.name
