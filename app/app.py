from flask import Flask, request, send_from_directory, jsonify

# --- USSD core import ---
try:
    from ussd import handle_ussd
except Exception:
    handle_ussd = None

import traceback
import sqlite3
import os
import re


# --- Roles schema for web cockpit (simple, local) ---
app = Flask(__name__)
def ensure_roles_schema(db_path: str):
    import sqlite3
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS user_roles (
        phone TEXT NOT NULL,
        primary_role TEXT NOT NULL,
        sub_role TEXT NOT NULL DEFAULT '',
        is_active INTEGER NOT NULL DEFAULT 0,
        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        PRIMARY KEY (phone, primary_role, sub_role)
    );
    """)
    con.commit()
    con.close()

def set_active_role(db_path: str, phone: str, primary: str, sub: str = "", village: str = "Church") -> None:
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    # Make sure table/cols exist (safe)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS user_roles (
      phone TEXT PRIMARY KEY,
      primary_role TEXT NOT NULL DEFAULT 'customer',
      sub_role TEXT NOT NULL DEFAULT '',
      village TEXT NOT NULL DEFAULT 'Church',
      updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """)
    cur.execute("""
    INSERT INTO user_roles(phone, primary_role, sub_role, village, updated_at)
    VALUES(?,?,?,?,datetime('now'))
    ON CONFLICT(phone) DO UPDATE SET
      primary_role=excluded.primary_role,
      sub_role=excluded.sub_role,
      village=excluded.village,
      updated_at=datetime('now')
    """, (phone, primary, sub or "", village or "Church"))
    con.commit()
    con.close()

def get_active_role(db_path: str, phone: str):
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    try:
        cur.execute("SELECT primary_role, sub_role, village FROM user_roles WHERE phone=? LIMIT 1", (phone,))
        row = cur.fetchone()
        if not row:
            return None
        primary, sub, village = row[0] or "customer", row[1] or "", row[2] or "Church"
        return (primary, sub, village)
    finally:
        con.close()

@app.route("/api/whoami", methods=["GET"])

def whoami():
    from flask import request, jsonify
    phone = (request.args.get("phone") or "").strip()
    village = (request.args.get("village") or "").strip()

    # normalize + handling (keep + if present)
    if phone and not phone.startswith("+") and phone.isdigit():
        phone = "+" + phone

    # Determine village: prefer explicit param; else keep current logic if you have it elsewhere
    # (We keep your current stored village logic by asking /ussd layer indirectly is expensive; so we keep param/fallback.)
    if not village:
        village = "Church"

    # Role selection priority:
    # 1) active role in user_roles (web tester switch)
    active = get_active_role(DB_PATH, phone) if phone else None
    # 2) infer from providers table if active not set
    inferred_primary, inferred_sub = "customer", ""
    try:
        con = sqlite3.connect(DB_PATH)
        cur = con.cursor()
        if phone:
            cur.execute("SELECT provider_type FROM providers WHERE phone=? LIMIT 1", (phone,))
            row = cur.fetchone()
            if row:
                ptype = (row[0] or "").strip()
                if ptype == "rider":
                    inferred_primary, inferred_sub = "provider", "rider"
                elif ptype == "business":
                    inferred_primary, inferred_sub = "provider", "business"
        con.close()
    except Exception:
        pass
    if active:
        primary, sub, village2 = active
        # if village param missing, take stored village
        if not village:
            village = village2
    else:
        primary, sub = (inferred_primary, inferred_sub)
    # Capabilities per role
    caps = []
    if primary == "customer":
        caps = ["home","nearest_riders","shops","listen_channels","my_channel","travel","switch_role"]
    elif primary == "provider" and sub == "rider":
        caps = ["home","delivery_inbox","accept_delivery","pickup","deliver","switch_role"]
    elif primary == "provider" and sub == "business":
        caps = ["home","shops","update_listing","switch_role"]
    elif primary == "traveler":
        caps = ["home","travel","switch_role"]
    else:
        caps = ["home","switch_role"]

    # USSD menu entrypoints used by the cockpit (these are shortcuts)
    menus = {
        "customer_home": "",
        "provider_home": "4",
        "provider_inbox": "4*2",
        "nearest_riders": "1",
        "shops": "2",
        "listen": "6",
        "my_channel": "7",
        "travel": "8"
    }

    # Available roles (hierarchy) – minimal but explicit
    available = [
        {"primary":"customer","sub":""},
        {"primary":"provider","sub":"rider"},
        {"primary":"provider","sub":"business"},
        {"primary":"traveler","sub":""},
    ]

    return jsonify({
        "ok": True,
        "phone": phone,
        "identity": {"village": village},
        "role": {"primary": primary, "sub": sub},
        "capabilities": caps,
        "menus": menus,
        "available_roles": available,
        "db": DB_PATH,
    })


@app.route("/api/set_role", methods=["POST"])
def api_set_role():
    from flask import request, jsonify
    village = (request.args.get("village") or request.form.get("village") or "Church").strip()

    phone = (request.args.get("phone") or request.form.get("phone") or "").strip()
    primary = (request.args.get("primary") or request.form.get("primary") or "").strip()
    sub = (request.args.get("sub") or request.form.get("sub") or "").strip()

    village = (request.args.get("village") or request.form.get("village") or "Church").strip()
    if phone and not phone.startswith("+") and phone.isdigit():
        phone = "+" + phone

    if not phone or not primary:
        return jsonify({"ok": False, "error": "phone and primary are required"}), 400
    village = (request.args.get("village") or request.form.get("village") or "Church").strip() or "Church"
    set_active_role(DB_PATH, phone, primary, sub, village=village)
    return jsonify({"ok": True, "phone": phone, "role": {"primary": primary, "sub": sub}})
@app.route("/api/state", methods=["GET"])
def api_state():
    phone = (request.args.get("phone","") or "").strip()
    out = {"ok": True, "phone": phone, "db": _db_path(), "counts": {}, "latest": {}}
    try:
        con = _conn()
        cur = con.cursor()
        # tables we care about
        tables = ["providers", "businesses", "delivery_requests", "channels", "messages"]
        for t in tables:
            try:
                cur.execute(f"SELECT COUNT(*) FROM {t}")
                out["counts"][t] = int(cur.fetchone()[0])
            except Exception:
                # table may not exist yet
                out["counts"][t] = None

        # latest deliveries
        try:
            cur.execute("""
                SELECT id, source_type, source_phone, pickup_village, pickup_landmark,
                       dropoff_village, dropoff_landmark, status, assigned_rider_phone, created_at
                FROM delivery_requests
                ORDER BY id DESC LIMIT 5
            """)
            out["latest"]["deliveries"] = cur.fetchall()
        except Exception:
            out["latest"]["deliveries"] = []

        con.close()
    except Exception as e:
        out["ok"] = False
        out["error"] = str(e)

    return jsonify(out), 200

@app.route("/api/seed_demo", methods=["POST"])
def api_seed_demo():
    """
    Seed minimal demo data for cockpit testing:
    - 3 riders (providers)
    - 2 businesses (if table exists)
    - 1 delivery request in 'new'
    """
    import sqlite3, datetime
    phone = (request.args.get("phone","") or "").strip()
    village = (request.args.get("village","Church") or "Church").strip()
    out = {"ok": True, "seeded": {}, "phone": phone, "village": village}
    try:
        con = _conn()
        cur = con.cursor()

        # providers table (riders)
        try:
            riders = [
                ("+254700000003","rider","Rider A",village,"SACCO-A","Water Pump",1),
                ("+254700000004","rider","Rider B",village,"SACCO-A","Unknown",1),
                ("+254700000002","rider","Rider C",village,"SACCO-B","Market Gate",1),
            ]
            for ph, ptype, name, vil, sacco, lm, avail in riders:
                cur.execute("""
                    INSERT INTO providers(phone, provider_type, name, village, sacco, current_landmark, is_available)
                    VALUES(?,?,?,?,?,?,?)
                    ON CONFLICT(phone) DO UPDATE SET
                      provider_type=excluded.provider_type,
                      name=excluded.name,
                      village=excluded.village,
                      sacco=excluded.sacco,
                      current_landmark=excluded.current_landmark,
                      is_available=excluded.is_available,
                      updated_at=datetime('now')
                """, (ph, ptype, name, vil, sacco, lm, avail))
            out["seeded"]["providers"] = len(riders)
        except Exception as e:
            out["seeded"]["providers"] = 0
            out["providers_error"] = str(e)

        # delivery_requests table
        try:
            src_phone = phone or "+23276000001"
            cur.execute("""
                INSERT INTO delivery_requests(source_type, source_phone, pickup_village, pickup_landmark,
                                              dropoff_village, dropoff_landmark, note, status)
                VALUES('customer', ?, ?, 'Bus station', ?, 'Water Pump', 'demo', 'new')
            """, (src_phone, village, village))
            out["seeded"]["delivery_requests"] = 1
        except Exception as e:
            out["seeded"]["delivery_requests"] = 0
            out["deliveries_error"] = str(e)

        con.commit()
        con.close()
    except Exception as e:
        out["ok"] = False
        out["error"] = str(e)

    return jsonify(out), 200

@app.route("/api/clear_demo", methods=["POST"])
def api_clear_demo():
    """
    Remove demo rows (safe, best-effort).
    """
    out = {"ok": True, "cleared": {}}
    try:
        con = _conn()
        cur = con.cursor()

        # remove demo riders
        try:
            cur.execute("DELETE FROM providers WHERE phone IN ('+254700000003','+254700000004','+254700000002')")
            out["cleared"]["providers"] = cur.rowcount
        except Exception as e:
            out["cleared"]["providers"] = 0
            out["providers_error"] = str(e)

        # remove demo deliveries (note='demo')
        try:
            cur.execute("DELETE FROM delivery_requests WHERE note='demo'")
            out["cleared"]["delivery_requests"] = cur.rowcount
        except Exception as e:
            out["cleared"]["delivery_requests"] = 0
            out["deliveries_error"] = str(e)

        con.commit()
        con.close()
    except Exception as e:
        out["ok"] = False
        out["error"] = str(e)

    return jsonify(out), 200


def api_state():
    phone = request.args.get("phone","").strip()
    if not phone:
        return jsonify({"ok": False, "err": "missing phone"}), 400

    # Normalize like your USSD flow (keep + if present)
    try:
        from ussd import normalize_phone
        nphone = normalize_phone(phone)
    except Exception:
        nphone = phone

    # Who am I / prefs
    role = "customer"
    village = "Church"
    try:
        import onboarding
        prefs = onboarding.get_prefs(nphone) or {}
        role = (prefs.get("role") or role).strip().lower()
        village = (prefs.get("landmark") or prefs.get("village") or village).strip() or village
    except Exception:
        pass

    out = {
        "ok": True,
        "phone": nphone,
        "role": role,
        "village": village,
        "nearest_riders": [],
        "delivery_open": [],
        "delivery_mine": [],
        "channels": [],
        "my_channel": None,
    }

    # Read DB
    try:
        conn = sqlite3.connect(BUMALA_DB_PATH)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # Nearest riders (simple heuristic: all available riders in same village/landmark)
        # providers schema: phone, provider_type, name, village, sacco, current_landmark, is_available
        try:
            rows = cur.execute("""
                SELECT phone, name, current_landmark, sacco, is_available
                FROM providers
                WHERE provider_type='rider'
                  AND COALESCE(is_available,1)=1
                ORDER BY datetime(updated_at) DESC
                LIMIT 20
            """).fetchall()
            for r in rows:
                out["nearest_riders"].append({
                    "phone": r["phone"],
                    "name": r["name"],
                    "landmark": r["current_landmark"],
                    "sacco": r["sacco"],
                    "eta_min": None,  # UI can simulate / later compute
                })
        except Exception:
            pass

        # Deliveries: open (unassigned) + mine (assigned to this rider)
        try:
            rows = cur.execute("""
                SELECT id, source_type, source_phone, pickup_landmark, dropoff_landmark,
                       status, assigned_rider_phone, created_at
                FROM delivery_requests
                WHERE status IN ('new','open','requested','pending','accepted','picked_up')
                ORDER BY id DESC
                LIMIT 30
            """).fetchall()
            for r in rows:
                item = {
                    "id": r["id"],
                    "from_phone": r["source_phone"],
                    "pickup": r["pickup_landmark"],
                    "dropoff": r["dropoff_landmark"],
                    "status": r["status"],
                    "assigned": r["assigned_rider_phone"],
                    "created_at": r["created_at"],
                }
                if (r["assigned_rider_phone"] or "").strip() == "":
                    out["delivery_open"].append(item)
                if (r["assigned_rider_phone"] or "").strip() == nphone:
                    out["delivery_mine"].append(item)
        except Exception:
            pass

        # Channels
        try:
            rows = cur.execute("""
                SELECT id, name, owner_phone, created_at
                FROM channels
                ORDER BY id DESC
                LIMIT 30
            """).fetchall()
            for r in rows:
                ch = {"id": r["id"], "name": r["name"], "owner": r["owner_phone"], "created_at": r["created_at"]}
                out["channels"].append(ch)
                if (r["owner_phone"] or "").strip() == nphone:
                    out["my_channel"] = ch
        except Exception:
            pass

        conn.close()
    except Exception as e:
        return jsonify({"ok": False, "err": str(e)}), 500

    return jsonify(out), 200

from flask import send_from_directory
import traceback



@app.route("/api/outixs_ticker", methods=["GET"])
def api_outixs_ticker():
    """
    Returns latest OUTIXs ledger events for the web ticker.
    """
    from flask import jsonify, request

    limit = int(request.args.get("limit", "25") or "25")
    if limit < 1: limit = 1
    if limit > 200: limit = 200

    db = _db_path()
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    cur.execute("""
        SELECT id, created_at, phone, event_type, ref_type, ref_id, amount, note, payload_json
        FROM outixs_events
        ORDER BY id DESC
        LIMIT ?
    """, (limit,))
    rows = [dict(r) for r in cur.fetchall()]
    con.close()

    # newest last for ticker readability
    rows = list(reversed(rows))
    return jsonify({"ok": True, "db": db, "events": rows})

@app.route("/tester", methods=["GET"])
def tester():
    return send_from_directory("static", "tester.html")

@app.route("/health", methods=["GET"])
def health():
    return ("ok", 200)

DB_PATH = os.environ.get("ANGELOPP_DB", "/opt/angelopp/data/bumala.db")
ensure_roles_schema(DB_PATH)
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
    text = (request.form.get("text", "") or "")

    try:
        if handle_ussd is None:
            app.logger.error('[USSD] handle_ussd import failed (ussd.py not loaded)')
            return ('END System error. Please try again.', 200)

        rv = handle_ussd(session_id=session_id, phone_number=phone_number, text=text)

        if rv is None:
            app.logger.exception("[USSD][EXC] handle_ussd returned None")
            return ("END System error. Please try again.", 200)

        # Flatten accidental nested tuples: ((body, code), code)
        if isinstance(rv, tuple) and len(rv) == 2 and isinstance(rv[0], tuple) and len(rv[0]) == 2:
            rv = rv[0]

        return rv
    except Exception:
        app.logger.exception("[USSD][EXC] System error in /ussd")
        return ("END System error. Please try again.", 200)

@app.route("/", methods=["GET"])
def index():
    # Web UI tester
    return send_from_directory("static", "tester.html")

@app.route("/health2", methods=["GET"], endpoint="health2")
def health2():
    return ("ok", 200)





# -----------------------------
# Web cockpit: tester + helpers
# -----------------------------


# --- WEB TESTER PANELS (debug cockpit) ---
from flask import jsonify
import traceback
from datetime import datetime

def _db_path():
    # keep aligned with ussd.py db
    return "/opt/angelopp/data/bumala.db"

def _q(sql, params=()):
    conn = sqlite3.connect(_db_path())
    try:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()

@app.route("/api/panels", methods=["GET"])
def api_panels():
    phone = (request.args.get("phone","") or "").strip()
    village = (request.args.get("village","") or "").strip()

    # if village not provided, try infer from phone (your whoami route already does similar)
    if not village:
        try:
            # best-effort: providers table may store village for business / rider
            rows = _q("SELECT village FROM providers WHERE phone=? LIMIT 1", (phone,))
            if rows and rows[0].get("village"):
                village = rows[0]["village"]
        except Exception:
            pass
    if not village:
        village = "Church"

    # “Nearest riders” panel (simple: available riders in same village)
    riders = _q("""
      SELECT phone, name, current_landmark, is_available
      FROM providers
      WHERE provider_type='rider'
        AND village=?
        AND COALESCE(is_available,1)=1
      ORDER BY
        CASE WHEN current_landmark IS NULL OR current_landmark='' THEN 99 ELSE 0 END,
        phone ASC
      LIMIT 10
    """, (village,))

    # Businesses panel
    businesses = _q("""
      SELECT phone, name, village, current_landmark
      FROM providers
      WHERE provider_type='business'
      ORDER BY created_at DESC
      LIMIT 10
    """)

    # Channels panel (schema depends on your channels table; try best-effort)
    channels = []
    try:
        channels = _q("""
          SELECT id, name, topic, created_at
          FROM channels
          ORDER BY created_at DESC
          LIMIT 10
        """)
    except Exception:
        try:
            channels = _q("SELECT id, name, created_at FROM channels ORDER BY created_at DESC LIMIT 10")
        except Exception:
            channels = []

    # Delivery requests panel (latest + open)
    deliveries_latest = _q("""
      SELECT id, source_type, source_phone, pickup_village, pickup_landmark,
             dropoff_village, dropoff_landmark, status, assigned_rider_phone, created_at
      FROM delivery_requests
      ORDER BY id DESC
      LIMIT 10
    """)

    deliveries_open = _q("""
      SELECT id, pickup_landmark, dropoff_landmark, status, assigned_rider_phone, created_at
      FROM delivery_requests
      WHERE COALESCE(status,'new') IN ('new','open','requested','pending','offered','accepted','picked_up')
      ORDER BY id DESC
      LIMIT 10
    """)

    return jsonify({
        "ok": True,
        "phone": phone,
        "village": village,
        "riders": riders,
        "businesses": businesses,
        "channels": channels,
        "deliveries": {
            "open": deliveries_open,
            "latest": deliveries_latest,
        }
    })


if __name__ == "__main__":
    # Dev server (nginx proxies to this)
    app.run(host="127.0.0.1", port=5002)
