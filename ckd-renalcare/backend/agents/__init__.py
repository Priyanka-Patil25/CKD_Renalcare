"""Agent hooks. Three small agents, each a plain function: dict in, dict out.
Right now they are rule-based (no LLM), so they run offline and are easy to test.
To make one an LLM agent, replace the body of run() and keep the same input/output shape.

  reader           -> reads the patient payload and writes a short factual history
  guideline_finder -> finds guideline passages (Postgres full-text search) for a question
  writer           -> drafts the visit summary from reader + guideline_finder output

Every call is saved in the agent_runs table (see run_agent below), so you can show it.
"""
import json
import db
from . import reader, guideline_finder, writer

REGISTRY = {"reader": reader, "guideline_finder": guideline_finder, "writer": writer}


def run_agent(name, payload_in, patient_id=None, visit_id=None):
    out, status = None, "ok"
    try:
        out = REGISTRY[name].run(payload_in)
    except Exception as e:
        out, status = {"error": str(e)[:300]}, "error"
    db.run("INSERT INTO agent_runs(patient_id, visit_id, agent, input, output, status) VALUES (%s,%s,%s,%s,%s,%s)",
           (patient_id, visit_id, name, json.dumps(payload_in, default=str)[:20000], json.dumps(out, default=str)[:20000], status))
    return out
