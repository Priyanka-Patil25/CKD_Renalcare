"""TOOLS = the only things an agent is allowed to do.

Each tool is a normal Python function plus a short description. The description is
what a real LLM reads to decide when to use the tool.

Rules for tools:
  * READ-ONLY for now. A tool never changes the patient record.
  * Return small, plain dictionaries (the LLM reads them).
  * The numbers (stage, flags, model score) come from our own code, never from the LLM.
"""
from dataclasses import dataclass
from typing import Callable
import service, screening
from agents import guideline_finder


@dataclass
class Tool:
    name: str
    description: str          # shown to the LLM
    params: dict              # parameter name -> short meaning
    fn: Callable
    brief: Callable           # one human sentence about the result (for the doctor's screen)


def _patient(study_id):
    p = service.build(study_id, persist=False, include_model=False)
    if not p:
        raise ValueError(f"No patient {study_id}")
    return p


# ---- the tools -------------------------------------------------------------
def get_patient_summary(study_id):
    p = _patient(study_id)
    k = p["kdigo"]
    return {"id": p["id"], "age": p["age"], "sex": p["sex"],
            "conditions": [n for n, v in p["conditions"].items() if v],
            "has_kidney_labs": k["egfr"] is not None or k["uacr"] is not None,
            "egfr": k["egfr"], "uacr": k["uacr"], "stage": k["stage_text"], "risk": k["risk"],
            "egfr_slope_per_year": k["egfr_slope"], "medicines": [m["drug"] for m in p["medicines"]],
            "visits_on_record": len(p["visits"])}


def get_care_gaps(study_id):
    p = _patient(study_id)
    return {"flags": [{"code": f["code"], "level": f["level"], "title": f["title"], "detail": f["detail"]} for f in p["flags"]]}


def run_screening_model(study_id):
    p = _patient(study_id)
    r = screening.predict(p["screening"]["inputs"])
    return {"level": r["level"], "message": r["message"], "missing_inputs": r["missing_inputs"],
            "top_factors": [f"{e['feature']} ({e['direction']})" for e in r["explanation"][:3]],
            "note": "Screening hint only. Used when there are no kidney labs."}


def search_guidelines(question):
    return guideline_finder.run({"question": question, "limit": 3})


TOOLS = {t.name: t for t in [
    Tool("get_patient_summary", "Get the patient's age, conditions, latest eGFR and uACR, KDIGO stage and risk, eGFR trend, medicines.",
         {"study_id": "patient ID, e.g. DEMO-001"}, get_patient_summary,
         lambda r: f"{r['stage']}" + (f", {r['risk']} risk" if r['risk'] else "") + (", no kidney labs on record" if not r['has_kidney_labs'] else "")),
    Tool("get_care_gaps", "List the care gaps (missing tests or medicines, unsafe medicines, fast decline) found by the guideline rules.",
         {"study_id": "patient ID"}, get_care_gaps,
         lambda r: f"{len(r['flags'])} care gap(s)" + (": " + "; ".join(f['title'] for f in r['flags'][:3]) if r['flags'] else "")),
    Tool("run_screening_model", "Run the random-forest screening model. Use ONLY for a patient with no eGFR/uACR. Returns low, watch or high.",
         {"study_id": "patient ID"}, run_screening_model,
         lambda r: f"screening level: {r['level']}"),
    Tool("search_guidelines", "Search the loaded guideline text (KDIGO) for passages that answer a question.",
         {"question": "plain question or keywords"}, search_guidelines,
         lambda r: f"{len(r['hits'])} guideline passage(s) found" if r["hits"] else "no guideline text found (none loaded yet)"),
]}


def specs():
    """What a real LLM is shown: name, description, parameters."""
    return [{"name": t.name, "description": t.description, "params": t.params} for t in TOOLS.values()]
