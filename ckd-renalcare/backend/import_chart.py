"""Load an OPD Master Chart (.xlsx) into Postgres.
One row per patient per visit. Same Patient Code on every visit of a patient.

    python import_chart.py data/OPD_Master_chart_SYNTHETIC_DEMO.xlsx --synthetic
    python import_chart.py my_real_chart.xlsx            (real, anonymised rows only: no names, no phone numbers)

Running it twice is safe: the same test on the same date is merged, not repeated.
"""
import argparse, math
from datetime import date
import pandas as pd
import db, service, caregaps as cg

COLS = {  # chart column -> observation code
    "Height (cm)": "height_cm", "Weight (kg)": "weight_kg", "Creatinine (mg/dL)": "creatinine",
    "eGFR (mL/min/1.73m2)": "egfr", "BUN (mg/dL)": "bun", "Sodium (mEq/L)": "sodium", "Potassium (mEq/L)": "potassium",
    "Calcium (mg/dL)": "calcium", "Phosphorus (mg/dL)": "phosphorus", "Blood Sugar / HbA1c": "hba1c",
    "Systolic BP": "sbp", "Diastolic BP": "dbp", "Serum Albumin (g/dL)": "albumin_serum", "Uric Acid (mg/dL)": "uric_acid",
}
ACR = "Protein / Albumin (ACR)"
MEDS = "Current Medicines (ACEi/ARB/SGLT2i/NSAID)"


def yn(x):
    return str(x).strip().upper() == "Y"


def num(x):
    try:
        v = float(x)
        return None if math.isnan(v) else v
    except (TypeError, ValueError):
        return None


def main(path, synthetic=False):
    d = pd.read_excel(path, header=4).dropna(subset=["Patient Code"])
    d["Visit Date"] = pd.to_datetime(d["Visit Date"]).dt.date
    n_pat = n_vis = 0
    for code, g in d.sort_values(["Patient Code", "Visit Date"]).groupby("Patient Code"):
        first, last = g.iloc[0], g.iloc[-1]
        sid = str(code).strip().upper()
        p = db.one("SELECT id FROM patients WHERE study_id=%s", (sid,))
        if not p:
            name = ("Demo patient " + sid.split("-")[-1]) if synthetic else None
            p = db.one("""INSERT INTO patients(study_id, display_name, sex, birth_year, diabetes, hypertension, heart_disease,
                          family_hx_kidney, dm_years, htn_years, is_synthetic) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                       (sid, name, str(first["Sex"]).strip().upper()[:1], first["Visit Date"].year - int(first["Age"]),
                        yn(last["Diabetes (Y/N)"]), yn(last["Hypertension (Y/N)"]), yn(last["Heart Disease (Y/N)"]),
                        yn(last["Family History Kidney Disease (Y/N)"]), num(last["DM Duration (yrs)"]), num(last["HTN Duration (yrs)"]),
                        synthetic))
            n_pat += 1
        pid = p["id"]
        for _, r in g.iterrows():
            vn = int(r["Visit Number"])
            v = db.one("SELECT id FROM visits WHERE patient_id=%s AND visit_no=%s", (pid, vn))
            if not v:
                v = db.one("""INSERT INTO visits(patient_id, visit_no, visit_date, status, reason, age_at_visit, doctor_stage)
                              VALUES (%s,%s,%s,'completed','Follow-up (chart)',%s,%s) RETURNING id""",
                           (pid, vn, r["Visit Date"], int(r["Age"]), None if pd.isna(r["CKD Stage (Doctor Assessed)"]) else str(r["CKD Stage (Doctor Assessed)"])))
                n_vis += 1
            vals = {code_: num(r[col]) for col, code_ in COLS.items() if col in r}
            vals["uacr"] = cg.parse_uacr(r[ACR]) if ACR in r else None
            service.add_results(sid, r["Visit Date"], vals, meds=None, visit_id=v["id"], source="chart")
            meds = [] if pd.isna(r[MEDS]) or str(r[MEDS]).strip().lower() in ("none", "nan", "") else \
                [m for m in str(r[MEDS]).replace("/", ",").split(",")]
            db.run("DELETE FROM visit_medications WHERE visit_id=%s", (v["id"],))
            for m in meds:
                if m.strip():
                    db.run("INSERT INTO visit_medications(visit_id, patient_id, drug, drug_class, compliant) VALUES (%s,%s,%s,%s,%s)",
                           (v["id"], pid, m.strip(), service.drug_class(m), yn(r["Medication Compliance (Y/N)"])))
            note = r.get("Doctor's Notes / Remarks")
            if isinstance(note, str) and note.strip() and not db.one("SELECT 1 FROM notes WHERE visit_id=%s", (v["id"],)):
                db.run("INSERT INTO notes(visit_id, body) VALUES (%s,%s)", (v["id"], note.strip()))
    print(f"imported: {n_pat} new patients, {n_vis} new visits")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("xlsx"); ap.add_argument("--synthetic", action="store_true")
    a = ap.parse_args()
    main(a.xlsx, a.synthetic)
