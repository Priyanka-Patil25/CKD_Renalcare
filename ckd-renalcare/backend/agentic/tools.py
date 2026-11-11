"""STEP 1: TOOLS.

A tool is just a normal Python function plus a short description. The description is what
the brain (the LLM) reads to decide when to use it.

Safety rules built in here:
  * Tools are READ-ONLY. None of them changes the patient record.
  * The patient is fixed by the system (ctx["study_id"]). The brain cannot ask for a
    different patient, even if it tries.
  * Names are never returned. The brain only sees the study ID.
"""
from dataclasses import dataclass
from typing import Callable
import service, screening
from rag.retrieve import retrieve


@dataclass
class Tool:
    name: str
    description: str          # written for the brain: WHEN to use it
    parameters: dict          # what the brain must send (JSON schema); {} = nothing
    fn: Callable              # fn(ctx, **args) -> dict

    def schema(self):
        """The format real LLM APIs expect when you tell them which tools exist."""
        return {"name": self.name, "description": self.description,
                "input_schema": {"type": "object", "properties": self.parameters, "required": list(self.parameters)}}


def _patient(ctx):
    p = service.build(ctx["study_id"], persist=False, include_model=False)
    if not p:
        raise ValueError("patient not found")
    return p


def get_patient_summary(ctx):
    p = _patient(ctx)
    k = p["kdigo"]
    return {
        "study_id": p["id"], "age": p["age"], "sex": p["sex"],
        "conditions": [n for n, v in p["conditions"].items() if v],
        "egfr": k["egfr"], "egfr_date": k["egfr_date"], "uacr": k["uacr"], "uacr_date": k["uacr_date"],
        "kdigo_stage": k["stage_text"], "kdigo_risk": k["risk"], "egfr_slope_per_year": k["egfr_slope"],
        "has_kidney_labs": k["egfr"] is not None or k["uacr"] is not None,
        "medicines": [m["drug"] for m in p["medicines"]],
        "visits_on_record": len(p["visits"]),
    }


def get_care_gaps(ctx):
    p = _patient(ctx)
    return {"flags": [{"code": f["code"], "level": f["level"], "title": f["title"],
                       "detail": f["detail"], "source": f["source"], "doctor_status": f["status"]} for f in p["flags"]]}


def run_screening_model(ctx):
    """Random forest. Only meaningful when the patient has NO eGFR/uACR."""
    p = _patient(ctx)
    inputs = p["screening"]["inputs"]
    if inputs.get("age") is None or not inputs.get("sex"):
        return {"error": "Not enough inputs (need at least age and sex)."}
    r = screening.predict(inputs)
    return {"applicable": p["screening"]["applicable"], "level": r["level"], "message": r["message"],
            "top_reasons": [f"{e['feature']} {e['direction']} the score" for e in r["explanation"][:3]],
            "inputs_missing": r["missing_inputs"], "disclaimer": r["disclaimer"]}


def search_guidelines(ctx, question):
    """RAG tool: finds the guideline passages closest to the question. Each passage carries its
    document name and page label (e.g. 'KDIGO 2024 CKD S197') so the answer can cite it."""
    hits = retrieve(question, k=3)
    return {"passages": [{"doc": h["doc"], "page": h["page"], "text": h["text"][:500]} for h in hits]}


TOOLS = {t.name: t for t in [
    Tool("get_patient_summary",
         "Get the patient's age, conditions, latest eGFR and uACR, KDIGO stage and risk, eGFR trend and medicines. ALWAYS call this first.",
         {}, get_patient_summary),
    Tool("get_care_gaps",
         "List the rule-based care gaps (overdue tests, missing or unsafe medicines, fast eGFR decline, referral, BP).",
         {}, get_care_gaps),
    Tool("run_screening_model",
         "Run the machine-learning screening model. Use ONLY when the patient has no eGFR or uACR. It says whether testing is worth ordering.",
         {}, run_screening_model),
    Tool("search_guidelines",
         "Search the stored guideline text for passages that answer a question. Returns passages with document and page.",
         {"question": {"type": "string", "description": "what to look up"}}, search_guidelines),
]}
