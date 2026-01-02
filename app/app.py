from flask import Flask, request, send_from_directory, jsonify
import sqlite3
import hashlib
import os
import re
from pathlib import Path

from ussd import handle_ussd, normalize_phone

print('[USSD] running file:', __file__, flush=True)

APP_DIR = Path(__file__).resolve().parent
PUBLIC_DIR = APP_DIR / "public"

app = Flask(__name__)

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
    session_id = request.form.get("sessionId", "") or ""
    phone_number = request.form.get("phoneNumber", "") or ""
    text = request.form.get("text", "") or ""
    rv = handle_ussd(session_id=session_id, phone_number=phone_number, text=text)

    # allow (body, code) or just body
    if isinstance(rv, tuple) and len(rv) == 2:
        return rv
    return (rv, 200)

# -----------------------------
# Public website + JSON endpoints
# -----------------------------
@app.route("/public")
@app.route("/public/")
def public_index():
    # Serve static HTML from ./public/index.html
    return send_from_directory(str(PUBLIC_DIR), "index.html")

@app.route("/public/latest")
def public_latest():
    # Option C: public feed reads ONLY from public_messages (explicitly published)
    category = (request.args.get("category", "Community") or "Community").strip()
    try:
        limit = int(request.args.get("limit", "50") or "50")
    except Exception:
        limit = 50
    limit = max(1, min(200, limit))

    if not is_category_public(category):
        return jsonify({"ok": True, "public": False, "category": category, "count": 0, "items": []})

    con = db()
    cur = con.cursor()
    cur.execute("""
        SELECT id, channel_id, category, author_anon, text, created_at, published_at
        FROM public_messages
        WHERE category=? AND COALESCE(is_hidden,0)=0
        ORDER BY id DESC
        LIMIT ?
    """, (category, limit))
    rows = cur.fetchall()
    con.close()

    items = []
    for r in rows:
        items.append({
            "id": r["id"],
            "channel_id": r["channel_id"],
            "category": r["category"],
            "author": r["author_anon"],
            "text": r["text"],
            "created_at": r["created_at"],
        })
    return jsonify({"ok": True, "public": True, "category": category, "count": len(items), "items": items})

@app.route("/public/stats")
def public_stats():
    # Stats over public_messages only
    con = db()
    cur = con.cursor()

    # total
    cur.execute("SELECT COUNT(*) AS c FROM public_messages WHERE COALESCE(is_hidden,0)=0")
    total = int(cur.fetchone()[0] or 0)

    # by category
    cur.execute("""
        SELECT category, COUNT(*) AS c
        FROM public_messages
        WHERE COALESCE(is_hidden,0)=0
        GROUP BY category
        ORDER BY c DESC
    """)
    by_category = [{"category": r[0], "count": int(r[1] or 0)} for r in cur.fetchall()]

    # last 14 days
    cur.execute("""
        SELECT substr(published_at,1,10) AS day, COUNT(*) AS c
        FROM public_messages
        WHERE COALESCE(is_hidden,0)=0
        GROUP BY day
        ORDER BY day DESC
        LIMIT 14
    """)
    rows = cur.fetchall()
    by_day = [{"day": r[0], "count": int(r[1] or 0)} for r in reversed(rows)]

    con.close()
    return jsonify({"ok": True, "total_messages": total, "by_category": by_category, "by_day_last_14": by_day})

if __name__ == "__main__":
    # dev server
    port = int(os.environ.get("PORT", "5002"))
    app.run(host="127.0.0.1", port=port)
