from flask import Flask, request, send_from_directory, jsonify
import re
import sqlite3
import hashlib
import os

from ussd import handle_ussd, normalize_phone

print('[USSD] running file:', __file__, flush=True)
app = Flask(__name__)

DB_PATH = os.environ.get("ANGELOPP_DB", "/opt/angelopp/data/bumala.db")

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
    t = re.sub(r'\b\d{10,}\b', lambda m: '[id-' + _mask_digits(m.group(0)) + ']', t)
    return t

def anon_user(phone: str) -> str:
    raw = (ANON_SALT + '|' + (phone or '')).encode('utf-8')
    return 'u_' + hashlib.sha256(raw).hexdigest()[:10]

def is_category_public(category: str) -> bool:
    cat = (category or '').strip()
    try:
        con = sqlite3.connect(DB_PATH)
        cur = con.cursor()
        cur.execute('SELECT is_public FROM public_policy WHERE category=?', (cat,))
        row = cur.fetchone()
        con.close()
        if not row:
            return False
        return int(row[0] or 0) == 1
    except Exception:
        return False

ANON_SALT = os.environ.get("ANGELOPP_ANON_SALT", "angelopp-public-v1")

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def anon_phone(phone: str) -> str:
    ph = normalize_phone(phone or "")
    h = hashlib.sha256((ANON_SALT + "|" + ph).encode("utf-8")).hexdigest()
    return "u_" + h[:10]  # korte stabiele pseudoniem

@app.route("/ussd", methods=["POST"])
def ussd():
    session_id = request.form.get("sessionId", "") or ""
    phone_number = request.form.get("phoneNumber", "") or ""
    text = request.form.get("text", "") or ""
    rv = handle_ussd(session_id=session_id, phone_number=phone_number, text=text)

    # Flatten accidental nested tuples: ((body, code), code)
    if isinstance(rv, tuple) and len(rv) == 2 and isinstance(rv[0], tuple) and len(rv[0]) == 2:
        rv = rv[0]
    if isinstance(rv, tuple) and len(rv) == 2:
        return rv
    return (str(rv), 200)

# ---------- Public transparency endpoints ----------
@app.route("/public")
def public_index():
    # static site in /opt/angelopp/app/public/index.html
    return send_from_directory("public", "index.html")

@app.route("/public/latest")
def public_latest():
    # public feed with policy + scrubbing
    limit = int(request.args.get('limit', '50') or 50)
    if limit > 200: limit = 200
    category = (request.args.get('category', '') or '').strip()

    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    params = []
    where = []

    # Only allow public categories
    if category:
        if not is_category_public(category):
            con.close()
            return jsonify({'ok': True, 'count': 0, 'items': []})
        where.append('category=?')
        params.append(category)
    else:
        # default: show only categories marked public
        where.append('category IN (SELECT category FROM public_policy WHERE is_public=1)')

    q = 'SELECT id, channel_id, category, author_phone, text, created_at FROM messages'
    if where:
        q += ' WHERE ' + ' AND '.join(where)
    q += ' ORDER BY id DESC LIMIT ?'
    params.append(limit)

    cur.execute(q, params)
    rows = cur.fetchall()
    con.close()

    items = []
    for (mid, channel_id, cat, author_phone, text, created_at) in rows:
        items.append({
            'id': mid,
            'channel_id': channel_id,
            'category': cat,
            'author': anon_user(author_phone),
            'text': scrub_public_text(text),
            'created_at': created_at,
        })

    return jsonify({'ok': True, 'count': len(items), 'items': items})
def public_stats():
    con = db()
    cur = con.cursor()

    cur.execute("SELECT COUNT(*) AS n FROM messages;")
    total_messages = cur.fetchone()["n"]

    cur.execute("""
        SELECT category, COUNT(*) AS n
        FROM messages
        GROUP BY category
        ORDER BY n DESC;
    """)
    by_category = [{"category": r["category"], "count": r["n"]} for r in cur.fetchall()]

    cur.execute("""
        SELECT date(created_at) AS day, COUNT(*) AS n
        FROM messages
        GROUP BY date(created_at)
        ORDER BY day DESC
        LIMIT 14;
    """)
    by_day = [{"day": r["day"], "count": r["n"]} for r in cur.fetchall()]

    con.close()
    return jsonify({
        "ok": True,
        "total_messages": total_messages,
        "by_category": by_category,
        "by_day_last_14": by_day
    })



# --- PUBLIC FEED ROUTES ---
# Make /public and /public/ both work and serve /public/index.html
from flask import send_from_directory, redirect

PUBLIC_DIR = os.path.join(os.path.dirname(__file__), "public")

@app.route("/public")
def public_root_no_slash():
    return redirect("/public/", code=302)

@app.route("/public/")
def public_root():
    return send_from_directory(PUBLIC_DIR, "index.html")


if __name__ == "__main__":
    # Dev server (behind nginx/uwsgi/gunicorn later if needed)
    app.run(host="127.0.0.1", port=5002)
