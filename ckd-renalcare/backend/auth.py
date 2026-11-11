"""Very small login system: pbkdf2 password hashes + random session tokens stored in Postgres.
Good enough for the project demo. For a real hospital deployment use the hospital's
single sign-on and HTTPS."""
import hashlib, hmac, os, secrets
from fastapi import Header, HTTPException
import db

ITER = 200_000


def hash_password(pw: str) -> str:
    salt = secrets.token_hex(8)
    h = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), ITER).hex()
    return f"pbkdf2${ITER}${salt}${h}"


def check_password(pw: str, stored: str) -> bool:
    try:
        _, it, salt, h = stored.split("$")
        got = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), int(it)).hex()
        return hmac.compare_digest(got, h)
    except Exception:
        return False


def login(username: str, password: str):
    u = db.one("SELECT * FROM staff WHERE username=%s", (username.strip().lower(),))
    if not u or not check_password(password, u["password_hash"]):
        return None
    token = secrets.token_urlsafe(32)
    db.run("INSERT INTO auth_sessions(token, staff_id, expires_at) VALUES (%s,%s, now() + interval '12 hours')",
           (token, u["id"]))
    return {"token": token, "role": u["role"], "name": u["full_name"], "username": u["username"]}


def current_staff(authorization: str = Header(default="")):
    token = authorization.removeprefix("Bearer ").strip()
    row = db.one("""SELECT s.id, s.username, s.full_name, s.role FROM auth_sessions a JOIN staff s ON s.id=a.staff_id
                    WHERE a.token=%s AND a.expires_at > now()""", (token,)) if token else None
    if not row:
        raise HTTPException(401, "Please log in")
    return row


def need(*roles):
    """Dependency factory: need('doctor') -> only doctors (admin always allowed)."""
    def dep(authorization: str = Header(default="")):
        s = current_staff(authorization)
        if s["role"] not in roles and s["role"] != "admin":
            raise HTTPException(403, f"This action is for: {', '.join(roles)}")
        return s
    return dep
