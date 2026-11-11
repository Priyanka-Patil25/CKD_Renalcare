"""Create the staff logins only. No demo patients are loaded.

Put this file in the backend folder (next to seed.py) and run:
    python create_users.py

Safe to re-run: it updates the password if the username already exists.
Change the passwords below (or set DOCTOR_PASSWORD / RECEPTION_PASSWORD) before real use.
"""
import os
import auth, db

USERS = [
    ("dr.morgan", "Dr. A. Morgan", "doctor", os.getenv("DOCTOR_PASSWORD", "doctor123")),
    ("reception1", "Reception desk", "reception", os.getenv("RECEPTION_PASSWORD", "reception123")),
]


def main():
    for username, full_name, role, password in USERS:
        db.run(
            """INSERT INTO staff(username, full_name, role, password_hash) VALUES (%s,%s,%s,%s)
               ON CONFLICT (username) DO UPDATE SET password_hash = EXCLUDED.password_hash""",
            (username, full_name, role, auth.hash_password(password)),
        )
        print(f"login ready: {username} ({role})")
    n = db.one("SELECT count(*) AS n FROM patients")["n"]
    print(f"patients in database: {n}")


if __name__ == "__main__":
    main()