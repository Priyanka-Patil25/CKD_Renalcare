"""Business logic: build a patient's history, run the rules and the model, save results."""
import json, random
from datetime import date, datetime
import db, kdigo, caregaps as cg, screening

CLASS_WORDS = {  # words in a medicine string -> drug_class
    "ACEi": {"acei", "ramipril", "enalapril", "lisinopril", "perindopril"},
    "ARB": {"arb", "telmisartan", "losartan", "olmesartan", "valsartan", "irbesartan"},
    "SGLT2i": {"sglt2i", "dapagliflozin", "empagliflozin", "canagliflozin"},
    "NSAID": {"nsaid", "ibuprofen", "diclofenac", "naproxen", "aceclofenac"},
    "metformin": {"metformin"},
}
UNITS = {"creatinine": "mg/dL", "egfr": "mL/min/1.73m2", "uacr": "mg/g", "bun": "mg/dL", "sodium": "mEq/L",
         "potassium": "mEq/L", "calcium": "mg/dL", "phosphorus": "mg/dL", "hba1c": "%", "albumin_serum": "g/dL",
         "uric_acid": "mg/dL", "sbp": "mmHg", "dbp": "mmHg", "height_cm": "cm", "weight_kg": "kg"}


def drug_class(name: str) -> str:
    w = {x for x in name.lower().replace("/", " ").replace(",", " ").split()}
    for cls, words in CLASS_WORDS.items():
        if w & words:
            return cls
    return "other"


def f(x):
    return None if x is None else float(x)


# ---------- queue ----------
def next_token(day: date) -> str:
    n = db.one("SELECT count(*) AS n FROM visits WHERE visit_date=%s", (day,))["n"]
    while db.one("SELECT 1 FROM visits WHERE visit_date=%s AND token=%s", (day, f"A-{n+1:02d}")):
        n += 1
    return f"A-{n+1:02d}"


def new_study_id() -> str:
    while True:
        sid = f"PT-{random.randint(10000, 99999)}"
        if not db.one("SELECT 1 FROM patients WHERE study_id=%s", (sid,)):
            return sid


def add_to_queue(patient_id: int, reason: str, age=None, day=None):
    day = day or date.today()
    ex = db.one("SELECT id FROM visits WHERE patient_id=%s AND visit_date=%s AND status IN ('waiting','in_consultation')",
                (patient_id, day))
    if ex:
        return ex["id"]
    vn = db.one("SELECT coalesce(max(visit_no),0)+1 AS n FROM visits WHERE patient_id=%s", (patient_id,))["n"]
    if age is None:
        by = db.one("SELECT birth_year FROM patients WHERE id=%s", (patient_id,))["birth_year"]
        age = day.year - by if by else None
    row = db.one("""INSERT INTO visits(patient_id, visit_no, visit_date, token, status, reason, age_at_visit)
                    VALUES (%s,%s,%s,%s,'waiting',%s,%s) RETURNING id""",
                 (patient_id, vn, day, next_token(day), reason, age))
    return row["id"]


def register(name, age, sex, reason, study_id=None):
    if study_id:
        p = db.one("SELECT * FROM patients WHERE study_id=%s", (study_id.strip().upper(),))
        if not p:
            raise ValueError(f"No patient with ID {study_id}")
    else:
        p = db.one("""INSERT INTO patients(study_id, display_name, sex, birth_year)
                      VALUES (%s,%s,%s,%s) RETURNING *""",
                   (new_study_id(), name.strip(), sex if sex in ("M", "F") else None,
                    date.today().year - int(age) if age else None))
    vid = add_to_queue(p["id"], reason, int(age) if age else None)
    return queue_row(vid)


def queue_row(visit_id):
    return db.one("""SELECT v.id AS visit_id, v.token, v.status, v.reason, v.visit_no, p.study_id AS id,
                            coalesce(p.display_name, p.study_id) AS name, coalesce(v.age_at_visit, %s - p.birth_year) AS age, p.sex
                     FROM visits v JOIN patients p ON p.id=v.patient_id WHERE v.id=%s""",
                  (date.today().year, visit_id))


def queue(day=None, with_clinical=False):
    day = day or date.today()
    rows = db.all("""SELECT v.id AS visit_id, v.token, v.status, v.reason, v.visit_no, p.id AS pid, p.study_id AS id,
                            coalesce(p.display_name, p.study_id) AS name, (v.submitted_at IS NOT NULL) AS submitted,
                            coalesce(v.age_at_visit, %s - p.birth_year) AS age, p.sex
                     FROM visits v JOIN patients p ON p.id=v.patient_id
                     WHERE v.visit_date=%s AND v.status <> 'cancelled' ORDER BY v.token""",
                  (date.today().year, day))
    for r in rows:
        r["is_follow_up"] = r["visit_no"] > 1
        if with_clinical:
            pl = build(r["id"], persist=False, include_model=False)
            r["risk"] = pl["kdigo"]["risk"]
            r["stage"] = pl["kdigo"]["stage_text"]
            r["flags_high"] = sum(1 for x in pl["flags"] if x["level"] == "high" and x["status"] == "pending")
            r["flags_open"] = sum(1 for x in pl["flags"] if x["status"] == "pending")
        del r["pid"]
    return rows


# ---------- history ----------
def series(pid):
    out = {}
    for r in db.all("SELECT code, value_num::float AS v, value_text AS t, observed_on AS d FROM observations "
                    "WHERE patient_id=%s ORDER BY observed_on", (pid,)):
        out.setdefault(r["code"], []).append({"date": r["d"].isoformat(), "value": r["v"], "text": r["t"]})
    return out


def latest(s, code):
    return s[code][-1] if s.get(code) else None


def build_visits(pid, patient, s, today):
    """Turn observations + visit medicines into the Visit objects the care-gap engine reads."""
    by_date = {}
    def at(d):
        return by_date.setdefault(d, cg.Visit(date=d, diabetes=patient["diabetes"], htn=patient["hypertension"]))
    for code, attr in (("egfr", "egfr"), ("uacr", "uacr"), ("sbp", "sbp")):
        for o in s.get(code, []):
            if o["value"] is not None:
                setattr(at(date.fromisoformat(o["date"])), attr, o["value"])
    meds_by_visit = {}
    for m in db.all("SELECT visit_id, drug, drug_class FROM visit_medications WHERE patient_id=%s", (pid,)):
        meds_by_visit.setdefault(m["visit_id"], set()).update({m["drug"].lower(), m["drug_class"].lower()})
    vrows = db.all("SELECT id, visit_date FROM visits WHERE patient_id=%s AND status <> 'cancelled' ORDER BY visit_date, visit_no", (pid,))
    for v in vrows:
        at(v["visit_date"])
    carried = set()
    for d in sorted(by_date):
        for v in vrows:
            if v["visit_date"] == d and v["id"] in meds_by_visit:
                carried = set()
                for w in meds_by_visit[v["id"]]:
                    carried |= cg.parse_meds(w)
                    carried.add(w)
        by_date[d].meds = set(carried)
    return list(by_date.values())


def sync_flags(pid, flags):
    """Save the engine's flags; keep what the doctor decided; close flags that no longer apply."""
    seen = set()
    for fl in flags:
        seen.add(fl.code)
        db.run("""INSERT INTO care_gap_flags(patient_id, code, level, title, detail, source)
                  VALUES (%s,%s,%s,%s,%s,%s)
                  ON CONFLICT (patient_id, code) DO UPDATE SET level=EXCLUDED.level, title=EXCLUDED.title,
                    detail=EXCLUDED.detail, source=EXCLUDED.source, updated_at=now(),
                    status = CASE WHEN care_gap_flags.status='resolved' THEN 'pending' ELSE care_gap_flags.status END""",
               (pid, fl.code, fl.level, fl.title, fl.detail, fl.source))
    db.run("UPDATE care_gap_flags SET status='resolved', updated_at=now() WHERE patient_id=%s AND status='pending' AND NOT (code = ANY(%s))",
           (pid, list(seen) or [""]))
    order = "CASE level WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END"
    return db.all(f"""SELECT id, code, level, title, detail, source, status, edited_text FROM care_gap_flags
                      WHERE patient_id=%s AND status <> 'resolved' ORDER BY {order}, id""", (pid,))


def screening_inputs(patient, s, age):
    def val(code):
        o = latest(s, code); return None if not o else o["value"]
    h, w = val("height_cm"), val("weight_kg")
    return {"age": age, "sex": patient["sex"], "bmi": round(w / (h / 100) ** 2, 1) if h and w else None,
            "sbp": val("sbp"), "dbp": val("dbp"), "bun": val("bun"), "uric_acid": val("uric_acid"),
            "calcium": val("calcium"), "albumin": val("albumin_serum"), "diabetes": "Y" if patient["diabetes"] else "N"}


def build(study_id, persist=True, include_model=True):
    p = db.one("SELECT * FROM patients WHERE study_id=%s", (study_id,))
    if not p:
        return None
    pid = p["id"]
    s = series(pid)
    today = date.today()
    visits = db.all("""SELECT id, visit_no, visit_date, status, reason, doctor_stage, age_at_visit, token FROM visits
                       WHERE patient_id=%s AND status <> 'cancelled' ORDER BY visit_date DESC, visit_no DESC""", (pid,))
    age = (today.year - p["birth_year"]) if p["birth_year"] else next((v["age_at_visit"] for v in visits if v["age_at_visit"]), None)
    e, u = latest(s, "egfr"), latest(s, "uacr")
    summ = kdigo.summary(e["value"] if e else None, u["value"] if u else None)
    summ["egfr_date"], summ["uacr_date"] = (e or {}).get("date"), (u or {}).get("date")
    cvisits = build_visits(pid, p, s, today)
    slope = cg.egfr_slope(cvisits)
    summ["egfr_slope"] = None if slope is None else round(slope, 1)
    last_date = max([v.date for v in cvisits] or [today])
    flags_raw = cg.evaluate(cvisits, max(today, last_date))
    flags = sync_flags(pid, flags_raw) if persist else _flags_preview(pid, flags_raw)

    cur_med = db.all("""SELECT DISTINCT ON (m.drug) m.drug, m.drug_class FROM visit_medications m JOIN visits v ON v.id=m.visit_id
                        WHERE m.patient_id=%s AND v.visit_date = (SELECT max(v2.visit_date) FROM visit_medications m2 JOIN visits v2 ON v2.id=m2.visit_id WHERE m2.patient_id=%s)""", (pid, pid))
    notes = db.all("""SELECT n.body, n.created_at, v.visit_date FROM notes n JOIN visits v ON v.id=n.visit_id
                      WHERE v.patient_id=%s ORDER BY n.created_at DESC LIMIT 20""", (pid,))
    payload = {
        "id": p["study_id"], "name": p["display_name"] or p["study_id"], "age": age, "sex": p["sex"],
        "conditions": {"diabetes": p["diabetes"], "hypertension": p["hypertension"],
                       "heart_disease": p["heart_disease"], "family_hx_kidney": p["family_hx_kidney"]},
        "is_synthetic": p["is_synthetic"],
        "kdigo": summ, "series": s,
        "visits": [{**v, "visit_date": v["visit_date"].isoformat()} for v in visits],
        "medicines": cur_med, "notes": [{**n, "created_at": n["created_at"].isoformat(), "visit_date": n["visit_date"].isoformat()} for n in notes],
        "flags": flags,
        "labs": [{"code": c, "value": latest(s, c)["value"], "unit": UNITS.get(c, ""), "date": latest(s, c)["date"]}
                 for c in ("egfr", "uacr", "creatinine", "hba1c", "potassium") if latest(s, c) and latest(s, c)["value"] is not None],
    }
    inputs = screening_inputs(p, s, age)
    payload["screening"] = {"applicable": not summ["ckd_range"] and e is None and u is None, "inputs": inputs, "result": None}
    if include_model and payload["screening"]["applicable"]:
        try:
            payload["screening"]["result"] = screening.predict(inputs)
        except Exception as ex:
            payload["screening"]["error"] = str(ex)[:150]
    if persist and (e or u):
        db.run("INSERT INTO risk_assessments(patient_id, egfr, uacr, g_cat, a_cat, kdigo_risk, egfr_slope) VALUES (%s,%s,%s,%s,%s,%s,%s)",
               (pid, summ["egfr"], summ["uacr"], summ["g"], summ["a"], summ["risk"], summ["egfr_slope"]))
    return payload


def _flags_preview(pid, flags_raw):
    saved = {r["code"]: r for r in db.all("SELECT code, status FROM care_gap_flags WHERE patient_id=%s", (pid,))}
    return [{"id": None, "code": fl.code, "level": fl.level, "title": fl.title, "detail": fl.detail, "source": fl.source,
             "status": saved.get(fl.code, {}).get("status", "pending") if saved.get(fl.code, {}).get("status") != "resolved" else "pending",
             "edited_text": None} for fl in flags_raw]


# ---------- entering results (one place for every report) ----------
RESULT_CODES = ["creatinine", "egfr", "uacr", "bun", "sodium", "potassium", "calcium", "phosphorus", "hba1c",
                "albumin_serum", "uric_acid", "sbp", "dbp", "height_cm", "weight_kg"]


def add_results(study_id, obs_date, values: dict, meds=None, visit_id=None, source="manual"):
    p = db.one("SELECT * FROM patients WHERE study_id=%s", (study_id,))
    if not p:
        raise ValueError("Unknown patient")
    pid = p["id"]
    values = {k: v for k, v in values.items() if k in RESULT_CODES and v not in (None, "")}
    if "creatinine" in values and "egfr" not in values:
        age = db.one("SELECT age_at_visit FROM visits WHERE patient_id=%s AND age_at_visit IS NOT NULL ORDER BY visit_date DESC LIMIT 1", (pid,))
        a = (age or {}).get("age_at_visit") or (obs_date.year - p["birth_year"] if p["birth_year"] else None)
        if a and p["sex"]:
            values["egfr"] = kdigo.egfr_ckdepi_2021(float(values["creatinine"]), a, p["sex"])
    added = updated = same = 0
    for code, v in values.items():
        v = float(v)
        old = db.one("SELECT id, value_num::float AS v FROM observations WHERE patient_id=%s AND code=%s AND observed_on=%s", (pid, code, obs_date))
        if old is None:
            db.run("INSERT INTO observations(patient_id, visit_id, code, value_num, unit, observed_on, source) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                   (pid, visit_id, code, v, UNITS.get(code), obs_date, source)); added += 1
        elif old["v"] == v:
            same += 1                                    # duplicate report: ignored
        else:
            db.run("UPDATE observations SET value_num=%s, source=%s WHERE id=%s", (v, source, old["id"])); updated += 1
    if meds is not None and visit_id:
        db.run("DELETE FROM visit_medications WHERE visit_id=%s", (visit_id,))
        for m in meds:
            if m.strip():
                db.run("INSERT INTO visit_medications(visit_id, patient_id, drug, drug_class) VALUES (%s,%s,%s,%s)",
                       (visit_id, pid, m.strip(), drug_class(m)))
    return {"added": added, "updated": updated, "duplicates_ignored": same, "egfr_calculated": "egfr" in values}


def decide_flag(flag_id, status, edited_text, staff_id):
    if status not in ("accepted", "edited", "dismissed", "pending"):
        raise ValueError("bad status")
    n = db.run("UPDATE care_gap_flags SET status=%s, edited_text=%s, decided_by=%s, decided_at=now(), updated_at=now() WHERE id=%s",
               (status, edited_text if status == "edited" else None, staff_id, flag_id))
    if not n:
        raise ValueError("Flag not found")
