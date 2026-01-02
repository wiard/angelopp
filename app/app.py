from flask import Flask, request, send_from_directory, jsonify
import sqlite3
import hashlib
import os

from ussd import handle_ussd, normalize_phone

print('[USSD] running file:', __file__, flush=True)
app = Flask(__name__)

DB_PATH = os.environ.get("ANGELOPP_DB", "/opt/angelopp/data/bumala.db")
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
    # public feed: we read from messages table (already used by channels in your logs)
    limit = int(request.args.get("limit", "50"))
    limit = max(1, min(limit, 200))

    con = db()
    cur = con.cursor()
    cur.execute("""
        SELECT id, category, author_phone, channel_id, text, created_at
        FROM messages
        ORDER BY id DESC
        LIMIT ?
    """, (limit,))
    rows = cur.fetchall()
    con.close()

    out = []
    for r in rows:
        out.append({
            "id": r["id"],
            "category": r["category"],
            "author": anon_phone(r["author_phone"]),
            "channel_id": r["channel_id"],
            "text": r["text"],
            "created_at": r["created_at"],
        })

    return jsonify({"ok": True, "count": len(out), "items": out})

@app.route("/public/stats")
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

if __name__ == "__main__":
    # Dev server (behind nginx/uwsgi/gunicorn later if needed)
    app.run(host="127.0.0.1", port=5002)
