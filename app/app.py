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
    # Default category is Community unless overridden
    category = (request.args.get("category") or "Community").strip()

    # Only show public categories
    if not is_category_public(category):
        return jsonify({"ok": True, "count": 0, "items": [], "category": category, "public": False})

    limit = int(request.args.get("limit") or 50)
    if limit < 1: limit = 1
    if limit > 200: limit = 200

    con = db()
    cur = con.cursor()
    cur.execute("""
      SELECT id, channel_id, category, author_phone, text, created_at
      FROM messages
      WHERE category = ?
      ORDER BY id DESC
      LIMIT ?
    """, (category, limit))
    rows = cur.fetchall()
    con.close()

    items = []
    for r in rows:
        items.append({
            "id": int(r["id"]),
            "channel_id": int(r["channel_id"]),
            "category": r["category"],
            "author": anon_user(str(r["author_phone"] or "")),
            "text": scrub_public_text(str(r["text"] or "")),
            "created_at": r["created_at"],
        })

    return jsonify({"ok": True, "category": category, "public": True, "count": len(items), "items": items})

@app.route("/public/stats")
def public_stats():
    # Aggregate only public categories
    con = db()
    cur = con.cursor()

    cur.execute("SELECT category FROM public_policy WHERE is_public=1")
    public_cats = [r["category"] for r in cur.fetchall()]
    if not public_cats:
        con.close()
        return jsonify({"ok": True, "total_messages": 0, "by_category": [], "by_day_last_14": []})

    # Total + by_category
    q_marks = ",".join(["?"] * len(public_cats))

    cur.execute(f"""
      SELECT category, COUNT(*) AS count
      FROM messages
      WHERE category IN ({q_marks})
      GROUP BY category
      ORDER BY count DESC
    """, public_cats)
    by_category = [{"category": r["category"], "count": int(r["count"])} for r in cur.fetchall()]

    cur.execute(f"""
      SELECT COUNT(*) AS total
      FROM messages
      WHERE category IN ({q_marks})
    """, public_cats)
    total = int(cur.fetchone()["total"])

    # Last 14 days by day (sqlite date)
    cur.execute(f"""
      SELECT date(created_at) AS day, COUNT(*) AS count
      FROM messages
      WHERE category IN ({q_marks})
        AND created_at >= datetime('now','-14 days')
      GROUP BY date(created_at)
      ORDER BY day ASC
    """, public_cats)
    by_day = [{"day": r["day"], "count": int(r["count"])} for r in cur.fetchall()]

    con.close()
    return jsonify({"ok": True, "total_messages": total, "by_category": by_category, "by_day_last_14": by_day})

if __name__ == "__main__":
    # dev server
    port = int(os.environ.get("PORT", "5002"))
    app.run(host="127.0.0.1", port=port)
