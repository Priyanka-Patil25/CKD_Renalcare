"""RenalCare / CKD decision support API.

Run:   uvicorn main:app --reload --port 8000        (from the backend folder)
Open:  http://localhost:8000          (the front end in ../public is served by this same app)
Docs:  http://localhost:8000/docs     (try every endpoint in the browser)
"""
from datetime import date, datetime
from pathlib import Path
from typing import Optional
from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import auth, db, intake, kdigo, screening, service, agents

@asynccontextmanager
async def lifespan(app):
    try:
        intake.ensure_columns()
    except Exception as e:
        print("could not check database columns (is DATABASE_URL right?):", e)
    try:
        screening.predict({"age": 50, "sex": "M"})       # loads model + SHAP once
    except Exception as e:
        print("model warm-up failed:", e)
    yield


app = FastAPI(title="RenalCare CKD decision support", version="0.1", lifespan=lifespan)
doctor = auth.need("doctor")
anyone = auth.current_staff
desk = auth.need("reception", "doctor")


# ---------- auth ----------
class Login(BaseModel):
    username: str
    password: str


@app.post("/api/login")
def login(b: Login):
    r = auth.login(b.username, b.password)
    if not r:
        raise HTTPException(401, "Wrong username or password")
    return r


@app.get("/api/me")
def me(s=Depends(anyone)):
    return s


@app.get("/api/health")
def health():
    m = screening.meta()
    return {"ok": True, "db": bool(db.one("SELECT 1 AS x")), "model": m["version"], "model_auc": m["test_auc"]}


# ---------- queue and registration ----------
@app.get("/api/queue")
def get_queue(s=Depends(desk)):
    return service.queue(with_clinical=(s["role"] in ("doctor", "admin")))


class Register(BaseModel):
    name: str = ""
    age: Optional[int] = None
    sex: Optional[str] = None
    reason: str = "Visit"
    study_id: Optional[str] = None         # fill this for a follow-up patient


@app.post("/api/patients")
def register(b: Register, s=Depends(desk)):
    try:
        if not b.study_id and not b.name.strip():
            raise ValueError("Name is required for a new patient")
        return service.register(b.name, b.age, (b.sex or "").upper()[:1], b.reason, b.study_id)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/patients/search")
def search(q: str = "", s=Depends(desk)):
    q = f"%{q.strip()}%"
    return db.all("""SELECT study_id AS id, coalesce(display_name, study_id) AS name, sex, birth_year FROM patients
                     WHERE study_id ILIKE %s OR display_name ILIKE %s ORDER BY study_id LIMIT 20""", (q, q))


# ---------- reception: clinical data entry and review ----------
class ClinicalEntry(BaseModel):
    visit_date: date
    visit_id: Optional[int] = None
    reason: Optional[str] = ""
    values: dict = {}
    conditions: dict = {}
    medicines: list[str] = []
    notes: Optional[str] = ""
    source: Optional[str] = "manual"


@app.get("/api/patients/{study_id}/intake")
def patient_intake(study_id: str, s=Depends(desk)):
    try:
        return intake.intake(study_id)
    except LookupError as e:
        raise HTTPException(404, str(e))


@app.post("/api/patients/{study_id}/clinical-entry")
def clinical_entry(study_id: str, b: ClinicalEntry, s=Depends(desk)):
    try:
        return intake.save_clinical_entry(study_id, b, s["id"])
    except LookupError as e:
        raise HTTPException(404, str(e))
    except (ValueError, TypeError) as e:
        raise HTTPException(400, str(e))


@app.post("/api/patients/{study_id}/visits/{visit_id}/submit-review")
def submit_review(study_id: str, visit_id: int, s=Depends(desk)):
    try:
        return intake.submit_review(study_id, visit_id, s["id"])
    except LookupError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


# ---------- doctor: patient history ----------
@app.get("/api/patients/{study_id}")
def patient(study_id: str, s=Depends(doctor)):
    p = service.build(study_id.upper())
    if not p:
        raise HTTPException(404, "Patient not found")
    db.run("INSERT INTO audit_log(staff_id, action, entity, entity_id) VALUES (%s,'view','patient',%s)", (s["id"], study_id))
    return p


class Results(BaseModel):
    date: date
    visit_id: Optional[int] = None
    values: dict                          # {"creatinine": 1.4, "uacr": 120, "sbp": 140, ...}
    medicines: Optional[list[str]] = None


@app.post("/api/patients/{study_id}/results")
def add_results(study_id: str, b: Results, s=Depends(doctor)):
    try:
        res = service.add_results(study_id.upper(), b.date, b.values, b.medicines, b.visit_id, source="manual")
    except (ValueError, TypeError) as e:
        raise HTTPException(400, str(e))
    return {"merge": res, "patient": service.build(study_id.upper())}


# ---------- doctor: visit actions ----------
@app.post("/api/visits/{visit_id}/start")
def start(visit_id: int, s=Depends(doctor)):
    db.run("UPDATE visits SET status='in_consultation' WHERE id=%s AND status='waiting'", (visit_id,))
    return {"ok": True}


class NoteIn(BaseModel):
    body: str


@app.post("/api/visits/{visit_id}/notes")
def save_note(visit_id: int, b: NoteIn, s=Depends(doctor)):
    if not b.body.strip():
        raise HTTPException(400, "Empty note")
    db.run("INSERT INTO notes(visit_id, staff_id, body) VALUES (%s,%s,%s)", (visit_id, s["id"], b.body.strip()))
    return {"saved": True, "at": datetime.now().isoformat(timespec="seconds")}


@app.post("/api/visits/{visit_id}/complete")
def complete(visit_id: int, s=Depends(doctor)):
    db.run("UPDATE visits SET status='completed' WHERE id=%s", (visit_id,))
    db.run("INSERT INTO audit_log(staff_id, action, entity, entity_id) VALUES (%s,'complete','visit',%s)", (s["id"], str(visit_id)))
    return {"completed": True}


# ---------- care gaps ----------
class Decision(BaseModel):
    status: str                           # accepted | edited | dismissed | pending
    edited_text: Optional[str] = None


@app.post("/api/flags/{flag_id}/decision")
def decide(flag_id: int, b: Decision, s=Depends(doctor)):
    try:
        service.decide_flag(flag_id, b.status, b.edited_text, s["id"])
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


# ---------- model ----------
@app.post("/api/screening")
def run_screening(inputs: dict, s=Depends(doctor)):
    try:
        res = screening.predict(inputs)
    except (ValueError, TypeError) as e:
        raise HTTPException(400, f"Bad input: {e}")
    return res


@app.get("/api/model")
def model_card(s=Depends(anyone)):
    return screening.meta()


@app.get("/api/kdigo/grid")
def grid():
    return kdigo.grid()


# ---------- RAG and agents ----------
class Ask(BaseModel):
    question: str
    patient_id: Optional[str] = None


@app.post("/api/rag/ask")
def rag(b: Ask, s=Depends(doctor)):
    from rag.retrieve import retrieve
    hits = [{**h, "section": None} for h in retrieve(b.question, 4)]
    if not hits:
        n = db.one("SELECT count(*) AS n FROM guideline_chunks")["n"]
        return {"answer": ("No guideline text is loaded yet. Run ingest_guidelines.py with the KDIGO PDFs."
                           if n == 0 else "No matching passage found. Try different words."),
                "citations": [], "mode": "retrieval-only"}
    return {"answer": "Most relevant guideline passages (retrieval only, no AI summary yet):\n\n" +
                      "\n\n".join(f"[{i+1}] {h['text']}" for i, h in enumerate(hits)),
            "citations": [{"n": i + 1, "doc": h["doc"], "page": h["page"], "section": None} for i, h in enumerate(hits)],
            "mode": "retrieval-only"}


@app.post("/api/patients/{study_id}/brief")
def brief(study_id: str, s=Depends(doctor)):
    """Reader -> guideline finder -> writer. Returns a draft summary for the doctor to edit."""
    p = service.build(study_id.upper())
    if not p:
        raise HTTPException(404, "Patient not found")
    pid = db.one("SELECT id FROM patients WHERE study_id=%s", (p["id"],))["id"]
    rd = agents.run_agent("reader", {"patient": p}, patient_id=pid)
    q = " ".join(f["title"] for f in p["flags"][:3]) or "chronic kidney disease monitoring"
    gf = agents.run_agent("guideline_finder", {"question": q, "limit": 3}, patient_id=pid)
    wr = agents.run_agent("writer", {"reader": rd, "flags": p["flags"], "hits": gf.get("hits", [])}, patient_id=pid)
    return {"draft": wr["draft"], "citations": wr["citations"]}


@app.post("/api/patients/{study_id}/pipeline")
def run_pipeline(study_id: str, s=Depends(doctor)):
    """Four agents in project-flow order: Clinical Data, Risk Assessment, Clinical Management, Diet Recommendation."""
    import orchestrator
    try:
        r = orchestrator.run(study_id.upper())
    except ValueError:
        raise HTTPException(404, "Patient not found")
    db.run("INSERT INTO audit_log(staff_id, action, entity, entity_id) VALUES (%s,'run_pipeline','patient',%s)", (s["id"], study_id.upper()))
    return r


@app.get("/api/patients/{study_id}/pipeline")
def last_pipeline(study_id: str, s=Depends(doctor)):
    import orchestrator
    return orchestrator.latest(study_id.upper()) or {"agents": [], "generated_at": None}


@app.post("/api/patients/{study_id}/agent")
def run_briefing_agent(study_id: str, s=Depends(doctor)):
    """The agent loop (agentic/): the brain picks read-only tools, we run them, it writes a
    briefing, a plain-code verifier checks it. The brain is Claude if ANTHROPIC_API_KEY is set,
    otherwise the scripted demo brain. Every step is saved in agent_runs."""
    from agentic.loop import run_agent as agentic_run
    from agentic.llm import get_brain
    sid = study_id.upper()
    if not db.one("SELECT 1 FROM patients WHERE study_id=%s", (sid,)):
        raise HTTPException(404, "Patient not found")
    goal = "Prepare a short, source-based briefing for the doctor about this patient."
    return agentic_run(goal, sid, get_brain())


class ReportText(BaseModel):
    text: str


@app.post("/api/patients/{study_id}/labs/propose")
def propose_labs(study_id: str, b: ReportText, s=Depends(doctor)):
    """Lab-reader agent: reads pasted report text and PROPOSES values. Saves nothing.
    The doctor confirms by calling POST /api/patients/{id}/results with the (edited) values."""
    from agentic.lab_reader import propose
    if not db.one("SELECT 1 FROM patients WHERE study_id=%s", (study_id.upper(),)):
        raise HTTPException(404, "Patient not found")
    return propose(b.text)


# ---------- links that pointed at pages that do not exist (they gave a 404) ----------
from fastapi import Request
from fastapi.responses import RedirectResponse
_MOVED = {"/reception-dashboard.html": "/reception.html", "/patient-search.html": "/reception.html#global-search",
          "/queue-workflow.html": "/reception.html#queue-patients-heading",
          "/reports-documents.html": "/reception.html", "/reception-account.html": "/reception.html"}


def _redirect(target):
    def go(request: Request):
        base, _, frag = target.partition("#")
        q = request.url.query
        return RedirectResponse(base + (("?" + q) if q else "") + (("#" + frag) if frag else ""), status_code=307)
    return go


for _src, _dst in _MOVED.items():
    app.add_api_route(_src, _redirect(_dst), methods=["GET"], include_in_schema=False)


# ---------- front end ----------
PUBLIC = Path(__file__).resolve().parent.parent / "public"
app.mount("/", StaticFiles(directory=PUBLIC, html=True), name="public")
