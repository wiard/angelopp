from flask import Flask, request, send_from_directory, jsonify
import sqlite3
import hashlib
import os
import re
import datetime
from pathlib import Path

from ussd import handle_ussd, normalize_phone

print('[USSD] running file:', __file__, flush=True)

APP_DIR = Path(__file__).resolve().parent
PUBLIC_DIR = APP_DIR / "public"

app = Flask(__name__)

from flask import send_from_directory

@app.route("/tester", methods=["GET"])
def tester():
    return send_from_directory("static", "tester.html")

@app.route("/health", methods=["GET"])
def health():
    return ("ok", 200)

DB_PATH = os.environ.get("ANGELOPP_DB", "/opt/angelopp/data/bumala.db")
ANON_SALT = os.environ.get("ANGELOPP_ANON_SALT", "angelopp-public-v1")

# -----------------------------
# Public feed: policy + scrubbing
# -----------------------------
_phone_re = re.compile(r'(?:\+?\d[\d\s\-().]{6,}\d)')
_email_re = re.compile(r'\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b', re.I)
_url_re   = re.compile(r'\bhttps?://\S+\b', re.I)

def _mask_digits(token: str) -> str:
    digits = re.sub(r'\D', '', token or '')
    if len(digits) < 7:
        return token
    return '•' * max(0, len(digits)-2) + digits[-2:]

def scrub_public_text(text: str) -> str:
    """Mask accidental PII in public pages (phones/emails/urls/long IDs)."""
    t = (text or '')
    t = _email_re.sub('[email-hidden]', t)
    t = _url_re.sub('[link-hidden]', t)

    def repl(m):
        return '[phone-' + _mask_digits(m.group(0)) + ']'

    t = _phone_re.sub(repl, t)
    # long digit blobs
    t = re.sub(r'\b\d{10,}\b', lambda m: '[id-' + _mask_digits(m.group(0)) + ']', t)
    return t

def anon_user(phone: str) -> str:
    raw = (ANON_SALT + '|' + (phone or '')).encode('utf-8')
    return 'u_' + hashlib.sha256(raw).hexdigest()[:10]

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def ensure_public_policy():
    con = db()
    cur = con.cursor()
    cur.execute("""
      CREATE TABLE IF NOT EXISTS public_policy (
        category TEXT PRIMARY KEY,
        is_public INTEGER NOT NULL DEFAULT 0,
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
      )
    """)
    # Default: Community public
    cur.execute("INSERT OR IGNORE INTO public_policy(category,is_public) VALUES('Community',1)")
    con.commit()
    con.close()

def is_category_public(category: str) -> bool:
    cat = (category or '').strip()
    con = db()
    cur = con.cursor()
    cur.execute("SELECT is_public FROM public_policy WHERE category=?", (cat,))
    row = cur.fetchone()
    con.close()
    return bool(row) and int(row["is_public"] or 0) == 1

ensure_public_policy()

# -----------------------------
# Core USSD endpoint
# -----------------------------
@app.route("/ussd", methods=["POST"])
def ussd():
    session_id = (request.form.get("sessionId", "") or "").strip()
    phone_number = (request.form.get("phoneNumber", "") or "").strip()
    text = (request.form.get("text", "") or "").strip()
    try:
        rv = handle_ussd(session_id=session_id, phone_number=phone_number, text=text)

        if rv is None:
            return ("END System error. Please try again.", 200)

        # Allow either:
        #  - string body
        #  - (body, status_code)
        #  - ((body, status_code), status_code)  (accidental nesting)
        if isinstance(rv, tuple) and len(rv) == 2 and isinstance(rv[0], tuple) and len(rv[0]) == 2:
            rv = rv[0]

        if isinstance(rv, tuple) and len(rv) == 2:
            body, code = rv
            return (str(body), int(code))

        # default: assume body-only
        return (str(rv), 200)

    except Exception as e:
        # Never crash the USSD gateway: return a safe END message
        return ("END System error. Please try again.", 200)

# -----------------------------
# Web UI tester & health check
# -----------------------------
@app.route("/", methods=["GET"])
def index():
    # Web UI tester
    return send_from_directory("static", "tester.html")

@app.route("/health2", methods=["GET"], endpoint="health2")
def health2():
    return ("ok", 200)

if __name__ == "__main__":
    # Dev server. In production, run behind nginx with a real WSGI server.
    port = int(os.environ.get("PORT", "5002"))
    # Ensure DB path is consistent
    os.environ.setdefault("ANGELOPP_DB", "/opt/angelopp/data/bumala.db")
    app.run(host="127.0.0.1", port=port, debug=False)



