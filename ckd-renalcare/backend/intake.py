"""Reception side of the workflow: clinical data entry, intake read-back, submit for doctor review.
Used by the Clinical Data Entry and Review & Submit pages."""
from datetime import date
import db, service

LABELS = {
    "sbp": "Systolic BP", "dbp": "Diastolic BP", "bun": "BUN", "uric_acid": "Uric acid", "calcium": "Calcium",
    "albumin_serum": "Serum albumin", "height_cm": "Height", "weight_kg": "Weight", "creatinine": "Serum creatinine",
    "egfr": "eGFR", "uacr": "uACR", "hba1c": "HbA1c", "potassium": "Potassium", "sodium": "Sodium",
    "phosphorus": "Phosphorus",
}
SUBMITTED_TEXT = "Submitted for doctor review"


def ensure_columns():
    """Lets an existing database pick up the new columns without re-running schema.sql."""
    db.run("ALTER TABLE visits ADD COLUMN IF NOT EXISTS submitted_at TIMESTAMPTZ")
    db.run("ALTER TABLE visits ADD COLUMN IF NOT EXISTS submitted_by BIGINT")


def _patient(study_id):
    p = db.one("SELECT * FROM patients WHERE study_id=%s", (study_id.strip().upper(),))
    if not p:
        raise LookupError("Patient not found")
    return p


def _status_text(v):
    if v["status"] == "completed":
        return "Completed"
    if v["status"] == "in_consultation":
        return "In consultation"
    if v.get("submitted_at"):
        return SUBMITTED_TEXT
    return "Draft - not yet submitted"


def _visit_payload(p, v):
    obs = db.all("""SELECT code, value_num::float AS value, unit, observed_on, source FROM observations
                    WHERE patient_id=%s AND (visit_id=%s OR observed_on=%s) ORDER BY code""",
                 (p["id"], v["id"], v["visit_date"]))
    meds = db.all("SELECT drug AS name, drug_class FROM visit_medications WHERE visit_id=%s ORDER BY id", (v["id"],))
    notes = db.all("SELECT body, created_at FROM notes WHERE visit_id=%s ORDER BY created_at", (v["id"],))
    return {
        "visit_id": v["id"], "id": v["id"], "visit_no": v["visit_no"], "token": v["token"],
        "visit_date": v["visit_date"].isoformat(), "reason": v["reason"], "status": _status_text(v),
        "queue_status": v["status"], "submitted": bool(v.get("submitted_at")),
        "observations": [{"key": o["code"], "code": o["code"], "label": LABELS.get(o["code"], o["code"]),
                          "value": o["value"], "unit": o["unit"] or "", "date": o["observed_on"].isoformat(),
                          "source": o["source"]} for o in obs],
        "medicines": meds,
        "notes": [{"body": n["body"], "created_at": n["created_at"].isoformat()} for n in notes],
    }


def intake(study_id):
    p = _patient(study_id)
    visits = db.all("""SELECT * FROM visits WHERE patient_id=%s AND status <> 'cancelled'
                       ORDER BY visit_date DESC, visit_no DESC""", (p["id"],))
    age = (date.today().year - p["birth_year"]) if p["birth_year"] else next(
        (v["age_at_visit"] for v in visits if v["age_at_visit"]), None)
    vp = [_visit_payload(p, v) for v in visits]
    return {
        "id": p["study_id"], "patient_id": p["study_id"], "name": p["display_name"] or p["study_id"],
        "age": age, "sex": p["sex"],
        "diabetes": p["diabetes"], "hypertension": p["hypertension"],
        "heart_disease": p["heart_disease"], "family_hx_kidney": p["family_hx_kidney"],
        "visits": vp, "status": vp[0]["status"] if vp else None,
    }


def save_clinical_entry(study_id, b, staff_id):
    p = _patient(study_id)
    vdate = b.visit_date
    if vdate > date.today():
        raise ValueError("Visit date cannot be in the future")

    visit = None
    if b.visit_id:
        visit = db.one("SELECT * FROM visits WHERE id=%s AND patient_id=%s", (b.visit_id, p["id"]))
    if not visit:
        visit = db.one("""SELECT * FROM visits WHERE patient_id=%s AND visit_date=%s AND status <> 'cancelled'
                          ORDER BY visit_no DESC LIMIT 1""", (p["id"], vdate))
    if visit and visit["status"] == "completed":
        raise ValueError("This visit is already completed and can no longer be edited")
    if not visit:
        vid = service.add_to_queue(p["id"], b.reason or "Visit", day=vdate)
        visit = db.one("SELECT * FROM visits WHERE id=%s", (vid,))
    vid = visit["id"]

    c = b.conditions or {}
    db.run("""UPDATE patients SET diabetes=%s, hypertension=%s, heart_disease=%s, family_hx_kidney=%s WHERE id=%s""",
           (bool(c.get("diabetes")), bool(c.get("hypertension")), bool(c.get("heart_disease")),
            bool(c.get("family_hx_kidney")), p["id"]))
    if b.reason:
        db.run("UPDATE visits SET reason=%s WHERE id=%s", (b.reason, vid))

    meds = [m for m in (b.medicines or []) if m.strip()]
    res = service.add_results(p["study_id"], vdate, b.values or {}, meds if meds else None, vid,
                              source=(b.source or "manual"))

    note = (b.notes or "").strip()
    if note:
        last = db.one("SELECT body FROM notes WHERE visit_id=%s ORDER BY created_at DESC LIMIT 1", (vid,))
        if not last or last["body"] != note:
            db.run("INSERT INTO notes(visit_id, staff_id, body) VALUES (%s,%s,%s)", (vid, staff_id, note))

    # an edit after submission needs to be submitted again
    db.run("UPDATE visits SET submitted_at=NULL, submitted_by=NULL WHERE id=%s AND status='waiting'", (vid,))
    db.run("INSERT INTO audit_log(staff_id, action, entity, entity_id) VALUES (%s,'clinical_entry','visit',%s)",
           (staff_id, str(vid)))
    return {"saved": True, "success": True, "visit_id": vid, "patient_id": p["study_id"],
            "visit_date": vdate.isoformat(), "observations": {
                "added": res["added"], "updated": res["updated"], "duplicates_ignored": res["duplicates_ignored"]}}


def submit_review(study_id, visit_id, staff_id):
    p = _patient(study_id)
    v = db.one("SELECT * FROM visits WHERE id=%s AND patient_id=%s", (visit_id, p["id"]))
    if not v or v["status"] == "cancelled":
        raise LookupError("Visit not found for this patient")
    if v["status"] == "completed":
        raise ValueError("This visit is already completed")
    db.run("UPDATE visits SET submitted_at=now(), submitted_by=%s WHERE id=%s", (staff_id, visit_id))
    db.run("INSERT INTO audit_log(staff_id, action, entity, entity_id) VALUES (%s,'submit_review','visit',%s)",
           (staff_id, str(visit_id)))
    return {"success": True, "submitted": True, "visit_id": visit_id, "patient_id": p["study_id"],
            "status": SUBMITTED_TEXT}
