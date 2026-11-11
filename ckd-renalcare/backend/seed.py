"""Create demo logins, load the synthetic chart and put a few patients in today's queue.

    python seed.py            (after:  psql -d ckd -f schema.sql)

Logins (change them!):  dr.morgan / doctor123      reception1 / reception123
"""
import os
from pathlib import Path
import auth, db, service, import_chart

HERE = Path(__file__).parent


def main():
    for u, name, role, pw in [("dr.morgan", "Dr. A. Morgan", "doctor", os.getenv("DOCTOR_PASSWORD", "doctor123")),
                              ("reception1", "Reception desk", "reception", os.getenv("RECEPTION_PASSWORD", "reception123"))]:
        db.run("""INSERT INTO staff(username, full_name, role, password_hash) VALUES (%s,%s,%s,%s)
                  ON CONFLICT (username) DO UPDATE SET password_hash=EXCLUDED.password_hash""", (u, name, role, auth.hash_password(pw)))
    import_chart.main(HERE / "data" / "OPD_Master_chart_SYNTHETIC_DEMO.xlsx", synthetic=True)
    for sid, why in [("DEMO-001", "Follow-up, reports"), ("DEMO-004", "Follow-up"), ("DEMO-007", "New: diabetes, high BP, no kidney tests"),
                     ("DEMO-006", "Follow-up")]:
        p = db.one("SELECT id FROM patients WHERE study_id=%s", (sid,))
        service.add_to_queue(p["id"], why)
    print("seeded. today's queue:", [r["token"] + " " + r["id"] for r in service.queue()])


if __name__ == "__main__":
    main()
