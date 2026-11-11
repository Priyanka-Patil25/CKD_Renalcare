"""Orchestrator: runs the four agents of the project workflow in order and builds one report.

  Clinical Data Agent  ->  Risk Assessment Agent  ->  Clinical Management Agent  ->  Diet Recommendation Agent

Rules (same as the project plan):
  * Plain code reads the numbers. No agent changes a clinical value, and no LLM is used here.
  * Management and Diet only quote KDIGO passages found by RAG, each with document and page.
    If nothing is found the agent says "insufficient evidence" and writes no advice.
  * Every output is a DRAFT that needs doctor review. One agent failing never hides the others.
Each agent call is saved in agent_runs; the whole report is saved as agent 'orchestrator'.
"""
import json
from datetime import date, datetime, timezone
import db
import service
from rag.retrieve import retrieve

NAMES = ["Clinical Data Agent", "Risk Assessment Agent", "Clinical Management Agent", "Diet Recommendation Agent"]
PRIMARY = "KDIGO 2024 CKD"          # preferred source; other loaded documents are only used if it has no match
STALE_DAYS = 365
DISCLAIMER = ("Decision support only. These are drafts that need clinician review. They are not a diagnosis or a prescription. "
              "Confirming CKD needs abnormal results that persist for more than 3 months.")


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _evidence(queries, per_query=2):
    """Retrieve passages for each topic. Prefer the primary guideline; label other sources clearly."""
    out, seen = [], set()
    for topic, q in queries:
        hits = retrieve(q, 8)
        hits = [h for h in hits if h["doc"] == PRIMARY] + [h for h in hits if h["doc"] != PRIMARY]
        ev = []
        for h in hits:
            if h["id"] in seen:
                continue
            seen.add(h["id"])
            ev.append({"doc": h["doc"], "page": h["page"], "text": " ".join(h["text"].split())[:420]})
            if len(ev) == per_query:
                break
        out.append({"topic": topic, "query": q, "evidence": ev})
    return out


# ---------------------------------------------------------------- agent 1
def clinical_data(p):
    """Which key values are on record, from when. Never changes a value."""
    latest = {}
    for pts_name, series in p["series"].items():
        pts = [x for x in (series or []) if x.get("value") is not None]
        if pts:
            latest[pts_name] = max(pts, key=lambda x: x["date"])
    k = p["kdigo"]
    want = [("egfr", "eGFR", "mL/min/1.73m2"), ("uacr", "uACR", "mg/g"), ("creatinine", "Creatinine", "mg/dL"),
            ("sbp", "Systolic BP", "mmHg"), ("potassium", "Potassium", "mEq/L")]
    if p["conditions"].get("diabetes"):
        want.append(("hba1c", "HbA1c", "%"))
    fields, warnings = [], []
    for key, label, unit in want:
        pt = latest.get(key)
        if not pt:
            fields.append({"name": label, "status": "missing", "value": None, "unit": unit, "date": None})
            warnings.append(f"{label} is not on record.")
            continue
        age = (date.today() - date.fromisoformat(pt["date"])).days
        st = "stale" if age > STALE_DAYS else "ok"
        fields.append({"name": label, "status": st, "value": pt["value"], "unit": unit, "date": pt["date"]})
        if st == "stale":
            warnings.append(f"{label} is {age} days old.")
    if k["uacr"] is None:
        warnings.append("Without uACR the albuminuria (A) category and the full KDIGO risk tier cannot be given.")
    status = "completed" if p["labs"] else "insufficient_evidence"
    return {"status": status, "summary": f"{sum(f['status'] != 'missing' for f in fields)} of {len(fields)} key values on record.",
            "inputs_used": ["saved results", "conditions", "medicines"], "fields": fields, "warnings": warnings}


# ---------------------------------------------------------------- agent 2
def risk_assessment(p):
    k, s = p["kdigo"], p["screening"]
    res = s.get("result") if s else None
    warnings = []
    out = {"inputs_used": ["latest eGFR", "latest uACR", "screening inputs"], "method": "KDIGO grid with CKD-EPI 2021 (rules); screening model only when there are no kidney labs"}
    if k["g"]:
        out.update(status="completed", stage=k["stage_text"], risk=k["risk"], egfr=k["egfr"], uacr=k["uacr"],
                   trend_per_year=k["egfr_slope"], monitor_months=k["monitor_months"],
                   summary=f"KDIGO {k['stage_text']}" + (f", {k['risk']} risk." if k["risk"] else ", risk cannot be graded without uACR."))
        if not k["a"]:
            warnings.append("uACR missing: risk tier is incomplete.")
    elif res:
        out.update(status="needs_review", stage=None, risk=None, summary=f"No kidney labs. Screening result: {res['level']}. It only suggests whether to test.")
    else:
        out.update(status="insufficient_evidence", stage=None, risk=None, summary="No eGFR, uACR or screening inputs to assess.")
    if res:
        out["screening"] = {"level": res["level"], "model_version": res.get("model_version"), "message": res["message"],
                            "factors": [{"feature": e["feature"], "direction": e["direction"], "value": round(e["value"], 3)} for e in res["explanation"][:5]]}
        warnings += res.get("warnings", [])
    out["limitations"] = "Screening result, not a diagnosis. The model was trained on US survey data (NHANES) and is not validated on this hospital's patients."
    out["warnings"] = warnings
    return out


# ---------------------------------------------------------------- agent 3
def clinical_management(p, risk):
    meds = " ".join(m["drug"].lower() for m in p["medicines"])
    topics = [("Monitoring", "monitoring frequency GFR albuminuria CKD heat map")]
    if p["kdigo"]["uacr"] is None:
        topics.append(("Missing uACR", "albuminuria testing urine albumin-to-creatinine ratio"))
    if p["conditions"].get("diabetes"):
        topics.append(("Diabetes and CKD", "SGLT2 inhibitor CKD type 2 diabetes eGFR"))
    if p["conditions"].get("hypertension"):
        topics.append(("Blood pressure", "blood pressure ACE inhibitor ARB albuminuria CKD"))
    if any(x in meds for x in ("nsaid", "diclofenac", "ibuprofen", "naproxen")):
        topics.append(("Medicines to review", "avoid NSAIDs nephrotoxic CKD"))
    groups = _evidence(topics)
    found = any(g["evidence"] for g in groups)
    gaps = [{"title": f["title"], "level": f["level"], "detail": f.get("edited_text") or f["detail"], "source": f["source"], "status": f["status"]} for f in p["flags"]]
    return {"status": "needs_review" if (found or gaps) else "insufficient_evidence",
            "summary": f"{len(gaps)} rule-based care gap(s) and {sum(len(g['evidence']) for g in groups)} guideline passage(s) for the doctor to review.",
            "inputs_used": ["risk assessment", "care gaps", "conditions", "medicines", "KDIGO guideline text (RAG)"],
            "care_gaps": gaps, "topics": groups,
            "warnings": [] if found else ["No guideline passage matched. Load the KDIGO PDFs with load_guidelines.py."]}


# ---------------------------------------------------------------- agent 4
def diet(p, risk):
    c, k = p["conditions"], p["kdigo"]
    meds = " ".join(m["drug"].lower() for m in p["medicines"])
    if not k["g"] and not (risk.get("screening") or {}).get("level") in ("watch", "high"):
        return {"status": "insufficient_evidence", "summary": "No kidney results or screening signal, so no diet considerations are drafted.",
                "inputs_used": ["kidney results"], "constraints": [], "topics": [], "warnings": []}
    topics, constraints = [("Protein intake", "protein intake CKD g/kg body weight")], []
    if c.get("hypertension"):
        topics.append(("Sodium", "dietary sodium intake CKD blood pressure")); constraints.append("Hypertension")
    if c.get("diabetes"):
        topics.append(("Diabetes", "diet glycemic control CKD diabetes")); constraints.append("Diabetes")
    pot = next((x for x in (p["series"].get("potassium") or []) if x.get("value") is not None), None)
    if (pot and max(x["value"] for x in p["series"]["potassium"]) >= 5.0) or any(x in meds for x in ("acei", "arb", "telmisartan", "losartan")):
        topics.append(("Potassium", "potassium intake hyperkalemia CKD diet")); constraints.append("Potassium and RAS-blocker medicine")
    if k["egfr"] is not None and k["egfr"] < 60:
        topics.append(("Healthy diet pattern", "plant-based diet CKD dietary patterns")); constraints.append(f"eGFR {k['egfr']}")
    groups = _evidence(topics, per_query=1)
    found = any(g["evidence"] for g in groups)
    return {"status": "needs_review" if found else "insufficient_evidence",
            "summary": f"{sum(len(g['evidence']) for g in groups)} guideline passage(s) on diet for the doctor and a dietitian to review.",
            "inputs_used": ["stage and risk", "conditions", "medicines", "potassium results", "KDIGO guideline text (RAG)"],
            "constraints": constraints, "topics": groups,
            "warnings": ["Not an independent diet prescription. A dietitian should individualise it."] + ([] if found else ["No guideline passage matched."])}


# ---------------------------------------------------------------- orchestrator
def _log(pid, agent, inp, out, status):
    db.run("INSERT INTO agent_runs(patient_id, agent, input, output, status) VALUES (%s,%s,%s,%s,%s)",
           (pid, agent, json.dumps(inp, default=str)[:20000], json.dumps(out, default=str)[:20000], status))


def run(study_id):
    p = service.build(study_id, persist=False, include_model=True)
    if not p:
        raise ValueError("No such patient")
    pid = db.one("SELECT id FROM patients WHERE study_id=%s", (study_id,))["id"]
    ctx, agents = {}, []
    steps = [(NAMES[0], lambda: clinical_data(p)), (NAMES[1], lambda: risk_assessment(p)),
             (NAMES[2], lambda: clinical_management(p, ctx[NAMES[1]])), (NAMES[3], lambda: diet(p, ctx[NAMES[1]]))]
    for name, fn in steps:
        started = _now()
        try:
            out = fn(); ctx[name] = out
        except Exception as e:                      # one failure must not hide the other agents
            out = {"status": "failed", "summary": "This agent did not complete.", "warnings": [str(e)[:200]]}
            ctx[name] = {}
        out.update(name=name, started_at=started, finished_at=_now(), review_required=True)
        _log(pid, name, {"study_id": study_id}, out, "error" if out["status"] == "failed" else "ok")
        agents.append(out)
    cites = []
    for a in agents[2:]:
        for g in a.get("topics", []):
            for e in g["evidence"]:
                c = f"{e['doc']}, PDF p.{e['page']}"
                if c not in cites:
                    cites.append(c)
    r2 = ctx[NAMES[1]]
    report = {"study_id": study_id, "generated_at": _now(), "agents": agents, "citations": cites,
              "headline": r2.get("summary", ""), "disclaimer": DISCLAIMER}
    _log(pid, "orchestrator", {"study_id": study_id}, report, "ok")
    return report


def latest(study_id):
    row = db.one("""SELECT a.output FROM agent_runs a JOIN patients p ON p.id=a.patient_id
                    WHERE p.study_id=%s AND a.agent='orchestrator' ORDER BY a.id DESC LIMIT 1""", (study_id,))
    if not row:
        return None
    o = row["output"]
    return json.loads(o) if isinstance(o, str) else o
