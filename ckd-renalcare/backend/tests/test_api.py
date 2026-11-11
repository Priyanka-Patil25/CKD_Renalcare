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
    assert r.status_code == 200
    return {"Authorization": "Bearer " + r.json()["token"]}


@pytest.fixture(scope="module")
def doc(client): return tok(client, "dr.morgan", "doctor123")


@pytest.fixture(scope="module")
def desk(client): return tok(client, "reception1", "reception123")


def test_login_rules(client, doc, desk):
    assert client.post("/api/login", json={"username": "dr.morgan", "password": "x"}).status_code == 401
    assert client.get("/api/queue").status_code == 401
    assert client.get("/api/patients/DEMO-001", headers=desk).status_code == 403   # reception cannot see clinical data
    assert client.get("/api/patients/DEMO-001", headers=doc).status_code == 200


def test_queue_roles(client, doc, desk):
    d = client.get("/api/queue", headers=doc).json()
    r = client.get("/api/queue", headers=desk).json()
    assert len(d) == len(r) >= 4 and "risk" in d[0] and "risk" not in r[0]


def test_patient_kdigo_and_flags(client, doc):
    p = client.get("/api/patients/DEMO-001", headers=doc).json()
    assert p["kdigo"]["stage_text"] == "G3b A2" and p["kdigo"]["risk"] == "very high"
    codes = {f["code"] for f in p["flags"]}
    assert "RAPID_DECLINE" in codes and "REFER" not in codes   # eGFR 40, uACR 260: not a KDIGO referral reason
    assert client.get("/api/patients/DEMO-003", headers=doc).json()["flags"] == []     # improving patient: no flags


def test_screening_only_for_no_labs(client, doc):
    assert client.get("/api/patients/DEMO-001", headers=doc).json()["screening"]["applicable"] is False
    s = client.get("/api/patients/DEMO-007", headers=doc).json()["screening"]
    assert s["applicable"] is True and s["result"]["level"] in ("low", "watch", "high")


def test_screening_endpoint_and_leakage_guard(client, doc):
    ok = client.post("/api/screening", headers=doc, json={"age": 60, "sex": "M", "bmi": 27, "sbp": 150, "dbp": 90, "diabetes": "Y"})
    assert ok.status_code == 200 and "explanation" in ok.json()
    import train_model
    assert not (set(train_model.NUM) | set(train_model.CAT)) & {"egfr", "serum_creatinine", "albumin_creatinine_ratio", "ckd"}


def test_register_new_and_followup_and_roles(client, desk, doc):
    r = client.post("/api/patients", headers=desk, json={"name": "Test Person", "age": 50, "sex": "F", "reason": "New"}).json()
    assert r["id"].startswith("PT-") and r["token"].startswith("A-")
    again = client.post("/api/patients", headers=desk, json={"study_id": r["id"], "reason": "dup"}).json()
    assert again["visit_id"] == r["visit_id"]                              # same day, no double queue entry
    assert client.post("/api/patients", headers=desk, json={"study_id": "NOPE-1", "reason": "x"}).status_code == 400


def test_results_merge_no_duplicates_and_medicine_rules(client, doc):
    q = {x["id"]: x for x in client.get("/api/queue", headers=doc).json()}
    v = q["DEMO-004"]["visit_id"]
    body = {"date": str(date.today()), "visit_id": v, "values": {"creatinine": 2.2, "uacr": 80, "sbp": 150},
            "medicines": ["Diclofenac", "Metformin", "ACEi"]}
    a = client.post("/api/patients/DEMO-004/results", headers=doc, json=body).json()
    assert a["merge"]["added"] >= 3 and a["merge"]["egfr_calculated"]
    codes = {f["code"] for f in a["patient"]["flags"]}
    assert "NSAID" in codes and ({"METFORMIN_DOSE", "METFORMIN_STOP"} & codes)
    b = client.post("/api/patients/DEMO-004/results", headers=doc, json=body).json()      # same report again
    assert b["merge"]["added"] == 0 and b["merge"]["duplicates_ignored"] >= 3


def test_flag_decision_is_kept(client, doc):
    p = client.get("/api/patients/DEMO-001", headers=doc).json()
    fid = p["flags"][0]["id"]
    assert client.post(f"/api/flags/{fid}/decision", headers=doc, json={"status": "edited", "edited_text": "Discussed, will refer"}).status_code == 200
    again = client.get("/api/patients/DEMO-001", headers=doc).json()
    f = next(x for x in again["flags"] if x["id"] == fid)
    assert f["status"] == "edited" and f["edited_text"] == "Discussed, will refer"
    assert client.post("/api/flags/999999/decision", headers=doc, json={"status": "accepted"}).status_code == 400


def test_notes_complete_and_brief(client, doc):
    q = {x["id"]: x for x in client.get("/api/queue", headers=doc).json()}
    v = q["DEMO-006"]["visit_id"]
    assert client.post(f"/api/visits/{v}/notes", headers=doc, json={"body": "BP discussed"}).json()["saved"]
    assert client.post(f"/api/visits/{v}/complete", headers=doc).json()["completed"]
    b = client.post("/api/patients/DEMO-006/brief", headers=doc).json()
    assert "HISTORY" in b["draft"] and "POINTS TO REVIEW" in b["draft"]


def test_rag_empty_then_loaded(client, doc):
    import db
    assert "No guideline text" in client.post("/api/rag/ask", headers=doc, json={"question": "ACE inhibitor albuminuria"}).json()["answer"]
    db.run("INSERT INTO guideline_chunks(doc, page, text) VALUES ('TEST DOC', 7, 'Use an ACE inhibitor or ARB in people with albuminuria and diabetes.')")
    r = client.post("/api/rag/ask", headers=doc, json={"question": "ACE inhibitor albuminuria"}).json()
    assert r["citations"][0]["doc"] == "TEST DOC" and r["citations"][0]["page"] == "7"
