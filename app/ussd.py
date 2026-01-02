from __future__ import annotations
# --- Relative distance engine ---
from relative_distance import PersonLocation, rank_drivers



# ============================================================
# Root menu village: read from user_prefs (fallback Church)
# ============================================================

def get_pref_village(phone: str, fallback: str = "Church") -> str:
    pnorm = normalize_phone(phone)
    try:
        conn = db()
        cur = conn.cursor()
        try:
            cur.execute("SELECT village FROM user_prefs WHERE phone=?", (pnorm,))
        except Exception:
            return fallback
        row = cur.fetchone()
        if not row:
            return fallback
        v = row[0] if isinstance(row, (list, tuple)) else row["village"]
        v = (v or "").strip() or fallback
        return v
    except Exception:
        return fallback

def village_name_from_choice(choice: str):
    c = str(choice).strip()
    for k, name in _village_pairs():
        if c == str(k):
            return name
    return None


# Toggle demo inputs for fairness ranking
FAIRNESS_DEMO_MODE = True


# /opt/bumala_riders/bumala_riders_ussd.py



# USSD display limits
MAX_LIST = 10

# === LANDMARK HELPERS ===

# ============================================================
# FAIRNESS_INTEGRATION_V1 (safe, optional)
# ============================================================
try:
    from policies.fairness import Candidate, PolicyWeights, rank_candidates
except Exception:
    Candidate = None
    PolicyWeights = None
    rank_candidates = None

try:
    from adapters.payments_adapter import DummyPaymentsAdapter
    from adapters.sms_adapter import DummySmsAdapter
    from adapters.voice_adapter import DummyVoiceAdapter
except Exception:
    DummyPaymentsAdapter = None
    DummySmsAdapter = None
    DummyVoiceAdapter = None

PAYMENTS = DummyPaymentsAdapter() if DummyPaymentsAdapter else None
SMS = DummySmsAdapter() if DummySmsAdapter else None
VOICE = DummyVoiceAdapter() if DummyVoiceAdapter else None




def _biz_village_pairs():
    """
    Returns list of (code, village_name) for menus.
    Tries VILLAGES and/or _village_pairs if present.
    """
    # Preferred: existing helper
    try:
        if "_village_pairs" in globals():
            vp = _village_pairs()
            out = []
            for item in vp:
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    out.append((str(item[0]), str(item[1])))
                else:
                    out.append((str(len(out)+1), str(item)))
            if out:
                return out
    except Exception:
        pass

    # Fallback: VILLAGES constant
    try:
        V = globals().get("VILLAGES")
        if V:
            out = []
            for item in V:
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    out.append((str(item[0]), str(item[1])))
                else:
                    out.append((str(len(out)+1), str(item)))
            if out:
                return out
    except Exception:
        pass

    # Last resort hardcoded
    return [("1","Bumala"), ("2","Butula"), ("3","Busia")]

def _biz_village_from_choice(choice: str) -> str:
    c = (choice or "").strip()
    if not c:
        return ""
    # numeric mapping
    if c.isdigit():
        pairs = _biz_village_pairs()
        idx = int(c) - 1
        if 0 <= idx < len(pairs):
            return pairs[idx][1]
        return ""
    # direct village name
    return c.strip().title()


def _to_float(x, default=None):
    try:
        return float(x)
    except Exception:
        return default


def _rank_riders_if_possible(riders):
    # riders can be list[dict] or list[tuple]; returns same shape, sorted
    if not riders or not rank_candidates or not Candidate:
        return riders

    cands = []
    original = []

    for r in riders:
        phone = None
        eta = None
        trust = 0.5
        recent = 0
        income = 0.0

        if isinstance(r, dict):
            phone = r.get("phone") or r.get("msisdn") or r.get("id")
            eta = _to_float(r.get("eta_minutes") or r.get("eta"))
            trust = float(r.get("trust_score", trust))
            recent = int(r.get("recent_jobs", recent))
            income = float(r.get("expected_income", income))
        elif isinstance(r, (tuple, list)) and len(r) >= 1:
            phone = str(r[0])
            if len(r) >= 2:
                eta = _to_float(r[1])
        else:
            continue

        if not phone:
            continue

        cands.append(Candidate(phone=str(phone), eta_minutes=eta, trust_score=trust, recent_jobs=recent, expected_income=income))
        original.append(r)

    ranked = rank_candidates(cands, PolicyWeights())

    # map by phone back to original entries
    by_phone = {}
    for r in riders:
        if isinstance(r, dict):
            k = r.get("phone") or r.get("msisdn") or r.get("id")
            if k: by_phone[str(k)] = r
        elif isinstance(r, (tuple, list)) and r:
            by_phone[str(r[0])] = r

    out = []
    for c in ranked:
        if c.phone in by_phone:
            out.append(by_phone[c.phone])

    # preserve leftovers
    seen = set()
    for o in out:
        if isinstance(o, dict):
            seen.add(str(o.get("phone") or o.get("msisdn") or o.get("id")))
        elif isinstance(o, (tuple, list)) and o:
            seen.add(str(o[0]))

    for r in riders:
        key = None
        if isinstance(r, dict):
            key = r.get("phone") or r.get("msisdn") or r.get("id")
        elif isinstance(r, (tuple, list)) and r:
            key = r[0]
        if key is None or str(key) not in seen:
            out.append(r)

    return out

def save_landmark(phone: str, name: str, description: str):
    import sqlite3
    db = sqlite3.connect(DB_PATH)
    cur = db.cursor()
    cur.execute(
        "INSERT INTO landmarks (phone, name, description) VALUES (?, ?, ?)",
        (phone, name, description)
    )
    db.commit()
    db.close()


import os
import re
import sqlite3
from dataclasses import dataclass
from typing import List, Tuple, Optional


# --- villages (used by businesses menu) ---
# pick_from_list() expects (key,label) pairs
VILLAGES = [
    ('1', 'Bumala'),
    ('2', 'Butula'),
    ('3', 'Busia'),
]

# === CHALLENGE_SCHEMA_V1 ===
import re

# Onboarding gate (role -> area -> landmark)
import onboarding

# ============================================================
# User prefs (role) - stored per phone
# ============================================================

def ensure_user_prefs(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS user_prefs (
        phone TEXT PRIMARY KEY,
        role TEXT NOT NULL DEFAULT 'customer',
        village TEXT NOT NULL DEFAULT 'Church',
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    );
    """)
    # migration: add missing columns safely (older DBs)
    try:
        cur.execute("ALTER TABLE user_prefs ADD COLUMN village TEXT NOT NULL DEFAULT 'Church';")
    except Exception:
        pass
    try:
        cur.execute("ALTER TABLE user_prefs ADD COLUMN created_at TEXT NOT NULL DEFAULT (datetime('now'));")
    except Exception:
        pass
    try:
        cur.execute("ALTER TABLE user_prefs ADD COLUMN updated_at TEXT NOT NULL DEFAULT (datetime('now'));")
    except Exception:
        pass
    conn.commit()

def provider_home_menu() -> str:
    lines = [
        'CON Service Provider',
        '1. My profile (register/update)',
        '2. My services (add/remove)',
        '3. Update my landmark',
        '4. Incoming requests',
        '9. Switch role',
        '0. Exit',
    ]
    return '\n'.join(lines)

def handle_role_switch(parts: list[str], phone: str) -> str:
    # parts[0] == '9'
    if len(parts) == 1:
        return '\n'.join([
            'CON Angelopp',
            '1. I am a Customer',
            '2. I am a Service Provider',
            '0. Exit',
        ])
    choice = (parts[1] if len(parts) >= 2 else '').strip()
    if choice == '1':
        set_user_role(phone, 'customer')
        return 'CON Role set ✓\nYou are now: Customer\n0. Back'
    if choice == '2':
        set_user_role(phone, 'provider')
        return 'CON Role set ✓\nYou are now: Service Provider\n0. Back'
    if choice == '0':
        return 'END Bye'
    return 'CON Invalid option.\n0. Back'

# --- UI icons (safe defaults) ---
ICON_GO = '->'
ICON_STAR = '*'
ICON_CHECK = 'OK'
ICON_DONE = "OK"


def _clean_text(s: str, max_len: int) -> str:
    s = (s or "").strip()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"[^0-9A-Za-z \-,'/().]", "", s)
    return s[:max_len].strip()

def ensure_challenge_schema():
    conn = db()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS daily_claims (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        phone TEXT NOT NULL,
        claim_date TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE(phone, claim_date)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS landmarks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        phone TEXT NOT NULL,
        village TEXT NOT NULL DEFAULT 'Bumala',
        name TEXT NOT NULL,
        description TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS points_ledger (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        phone TEXT NOT NULL,
        pts INTEGER NOT NULL,
        reason TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """)

    conn.commit()
    conn.close()



def ensure_messages(conn: sqlite3.Connection) -> None:
    """
    Ensure messages table exists with a 'text' column.
    Safe migrations: if table exists but text missing, add it.
    """
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_id INTEGER NOT NULL,
            category TEXT NOT NULL DEFAULT '',
            author_phone TEXT NOT NULL DEFAULT '',
            text TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
    """)
    cur.execute("PRAGMA table_info(messages);")
    cols = [r[1] for r in cur.fetchall()]
    if "text" not in cols:
        try: cur.execute("ALTER TABLE messages ADD COLUMN text TEXT NOT NULL DEFAULT '';")
        except Exception: pass
    if "category" not in cols:
        try: cur.execute("ALTER TABLE messages ADD COLUMN category TEXT NOT NULL DEFAULT '';")
        except Exception: pass
    conn.commit()

def _add_points(phone: str, pts: int, reason: str):
    conn = db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO points_ledger(phone, pts, reason) VALUES (?, ?, ?)",
        (phone, int(pts), (reason or "")[:40])
    )
    conn.commit()
    conn.close()

def _mark_claim_today(phone: str) -> bool:
    conn = db()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO daily_claims(phone, claim_date) VALUES (?, date('now'))",
            (phone,)
        )
        conn.commit()
        ok = True
    except Exception:
        ok = False
    conn.close()
    return ok

def _added_landmark_today(phone: str) -> bool:
    """Return True if this phone already added a landmark today.
    Uses absolute DB path to avoid 'wrong working directory' surprises.
    """
    import sqlite3
    db = sqlite3.connect(DB_PATH)
    try:
        cur = db.cursor()
        cur.execute(
            """
            SELECT 1
            FROM landmarks
            WHERE phone = ?
              AND date(created_at) = date('now')
            LIMIT 1
            """,
            (phone,)
        )
        return cur.fetchone() is not None
    finally:
        db.close()

# --- constants (auto-added) ---
DB_PATH = '/opt/angelopp/data/bumala.db'
# ------------------------------


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_schema() -> None:
    conn = db()
    cur = conn.cursor()

    # Riders directory
    cur.execute("""
    CREATE TABLE IF NOT EXISTS riders (
        phone TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        village TEXT NOT NULL,
        rider_type TEXT NOT NULL,
        sacco TEXT DEFAULT '',
        location TEXT DEFAULT '',
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now'))
    )
    """)

    # Customers (optional)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS customers (
        phone TEXT PRIMARY KEY,
        name TEXT DEFAULT '',
        village TEXT DEFAULT '',
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now'))
    )
    """)

    # Businesses directory (Yellow Pages)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS businesses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        owner_phone TEXT NOT NULL,
        name TEXT NOT NULL,
        category TEXT NOT NULL,
        village TEXT NOT NULL,
        location TEXT DEFAULT '',
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now'))
    )
    """)

    cur.execute("CREATE INDEX IF NOT EXISTS idx_businesses_village ON businesses(village)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_businesses_category ON businesses(category)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_businesses_owner ON businesses(owner_phone)")

    # Landmarks (community map)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS landmarks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        village TEXT NOT NULL,
        name TEXT NOT NULL,
        added_by TEXT NOT NULL,
        created_at TEXT DEFAULT (datetime('now'))
    )
    """)
    # Landmarks indexes
    cur.execute("CREATE INDEX IF NOT EXISTS idx_landmarks_village ON landmarks(village)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_landmarks_added_by ON landmarks(added_by)")


    # =========================================================
    # Channels (community micro-radio) — MVP
    # =========================================================
    cur.execute("""
    CREATE TABLE IF NOT EXISTS channels (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        owner_phone TEXT NOT NULL,
        name TEXT NOT NULL,
        category TEXT NOT NULL DEFAULT 'Community',
        is_active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_channels_owner ON channels(owner_phone)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_channels_category ON channels(category)")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS channel_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        channel_id INTEGER NOT NULL,
        text TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY(channel_id) REFERENCES channels(id)
    )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_channel_messages_channel ON channel_messages(channel_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_channel_messages_created ON channel_messages(created_at)")


    # -----------------------------
    # Channels (text-only micro radio)
    # -----------------------------
    cur.execute("""
    CREATE TABLE IF NOT EXISTS channels (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        owner_phone TEXT NOT NULL,
        name TEXT NOT NULL,
        category TEXT NOT NULL DEFAULT 'Community',
        is_active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """)

    cur.execute("CREATE INDEX IF NOT EXISTS idx_channels_owner_active ON channels(owner_phone, is_active)")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS channel_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        channel_id INTEGER NOT NULL,
        sender_phone TEXT NOT NULL,
        message TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY(channel_id) REFERENCES channels(id)
    )
    """)

    cur.execute("CREATE INDEX IF NOT EXISTS idx_channel_messages_channel ON channel_messages(channel_id, created_at)")


    # Points / Challenge rewards
    cur.execute("""
    CREATE TABLE IF NOT EXISTS points (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        phone TEXT NOT NULL,
        reason TEXT NOT NULL,
        pts INTEGER NOT NULL,
        created_at TEXT DEFAULT (datetime('now'))
    )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_points_phone ON points(phone)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_points_created_at ON points(created_at)")

    # Callback requests (future AT voice callback / or manual SACCO-assisted)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS callback_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT NOT NULL,
        customer_phone TEXT NOT NULL,
        target_phone TEXT NOT NULL,
        target_kind TEXT NOT NULL,  -- 'rider' or 'business'
        village TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'NEW',
        created_at TEXT DEFAULT (datetime('now'))
    )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_callbacks_status ON callback_requests(status)")

    conn.commit()
    conn.close()


# =========================
# USSD UTIL
# =========================

def digits_only(s: str) -> str:
    return re.sub(r"\D+", "", s or "")


def normalize_phone(phone: str) -> str:
    # Accept "+2547..." etc; store digits with leading +
    p = phone.strip()
    if p.startswith("+"):
        return "+" + digits_only(p)
    d = digits_only(p)
    if d.startswith("254"):
        return "+" + d
    if d.startswith("0") and len(d) >= 10:
        return "+254" + d[1:]
    # fallback
    return "+" + d


def parse_text(text: str) -> List[str]:
    if not text:
        return []
    return text.split("*")


def ussd_response(msg: str) -> str:
    # Ensure it starts with CON/END as-is
    return msg


def mask_phone(phone: str) -> str:
    p = normalize_phone(phone)
    d = digits_only(p)
    if len(d) < 6:
        return p
    # show last 3 digits only
    return f"+{d[:3]}***{d[-3:]}"


def pick_from_list(title: str, items: List[Tuple[str, str]]) -> str:
    lines = [f"CON {title}"]
    for k, v in items:
        lines.append(f"{k}. {v}")
    lines.append("0. Back")
    return "\n".join(lines)


def main_menu(phone: str = "") -> str:
    v = get_pref_village(phone, fallback="Church") if phone else "Church"
    return "\n".join([
        "CON Bumala Directory",
        f"1. Find a Rider {ICON_GO}",
        "2. Local Businesses",
        "3. Register (Rider / Business)",
        f"4. Today’s Challenge {ICON_STAR}",
        f"5. Set my location",
        "0. Exit",
    ])


def village_menu(title: str = "Choose village:") -> str:
    return pick_from_list(title, _village_pairs())
def category_menu(title: str = "Choose category:") -> str:
    return pick_from_list(title, BUSINESS_CATEGORIES)


def rider_type_menu(title: str = "Rider type:") -> str:
    return pick_from_list(title, RIDER_TYPES)


def village_key_to_name(k: str) -> str:
    for kk, name in VILLAGES:
        if kk == k:
            return name
    return "Bumala"


def category_key_to_name(k: str) -> str:
    for kk, name in BUSINESS_CATEGORIES:
        if kk == k:
            return name
    return "Shop / Duka"


def rider_type_key_to_name(k: str) -> str:
    for kk, name in RIDER_TYPES:
        if kk == k:
            return name
    return "Boda"


# =========================
# DIRECTORY QUERIES
# =========================

def upsert_rider(phone: str, name: str, village: str, rider_type: str, sacco: str = "", location: str = "") -> None:
    conn = db()
    cur = conn.cursor()
    cur.execute("""
    INSERT INTO riders (phone, name, village, rider_type, sacco, location, created_at, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
    ON CONFLICT(phone) DO UPDATE SET
        name=excluded.name,
        village=excluded.village,
        rider_type=excluded.rider_type,
        sacco=excluded.sacco,
        location=excluded.location,
        updated_at=datetime('now')
    """, (phone, name, village, rider_type, sacco, location))
    conn.commit()
    conn.close()


def insert_business(owner_phone: str, name: str, category: str, village: str, location: str = "") -> None:
    conn = db()
    cur = conn.cursor()
    cur.execute("""
    INSERT INTO businesses (owner_phone, name, category, village, location, created_at, updated_at)
    VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))
    """, (owner_phone, name, category, village, location))
    conn.commit()
    conn.close()


def list_riders_by_village(village: str, limit: int = MAX_LIST) -> List[sqlite3.Row]:
    conn = db()
    cur = conn.cursor()
    cur.execute("""
    SELECT phone, name, rider_type, sacco, location
    FROM riders
    WHERE village = ?
    ORDER BY updated_at DESC
    LIMIT ?
    """, (village, limit))
    rows = cur.fetchall()
    conn.close()
    return rows


def list_businesses(village: str, category: str, limit: int = MAX_LIST) -> List[sqlite3.Row]:
    conn = db()
    cur = conn.cursor()
    cur.execute("""
    SELECT id, name, owner_phone, location
    FROM businesses
    WHERE village = ? AND category = ?
    ORDER BY updated_at DESC
    LIMIT ?
    """, (village, category, limit))
    rows = cur.fetchall()
    conn.close()
    return rows


def display_name(phone: str) -> str:
    phone = normalize_phone(phone)
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT name FROM riders WHERE phone = ?", (phone,))
    row = cur.fetchone()
    conn.close()
    if row and row["name"]:
        return row["name"]
    return mask_phone(phone)


# =========================
# CHALLENGE / POINTS
# =========================

def award_points(phone: str, reason: str, pts: int) -> None:
    phone = normalize_phone(phone)
    conn = db()
    cur = conn.cursor()
    cur.execute("INSERT INTO points (phone, reason, pts, created_at) VALUES (?, ?, ?, datetime('now'))",
                (phone, reason, int(pts)))
    conn.commit()
    conn.close()


def has_claimed_today(phone: str, reason: str) -> bool:
    phone = normalize_phone(phone)
    conn = db()
    cur = conn.cursor()
    cur.execute("""
    SELECT 1
    FROM points
    WHERE phone = ? AND reason = ?
      AND date(created_at) = date('now')
    LIMIT 1
    """, (phone, reason))
    ok = cur.fetchone() is not None
    conn.close()
    return ok


def add_landmark(phone: str, village: str, name: str) -> None:
    phone = normalize_phone(phone)
    conn = db()
    cur = conn.cursor()
    cur.execute("""
    INSERT INTO landmarks (village, name, added_by, created_at)
    VALUES (?, ?, ?, datetime('now'))
    """, (village, name.strip(), phone))
    conn.commit()
    conn.close()


def weekly_leaderboard(days: int = 7, limit: int = 3) -> str:
    conn = db()
    cur = conn.cursor()

    # Landmarks per village (last N days)
    cur.execute(f"""
    SELECT village, COUNT(*) AS c
    FROM landmarks
    WHERE datetime(created_at) >= datetime('now', '-{int(days)} days')
    GROUP BY village
    ORDER BY c DESC
    LIMIT ?
    """, (limit,))
    lm_rows = cur.fetchall()

    # Helper points (last N days)
    cur.execute(f"""
    SELECT phone, SUM(pts) AS s
    FROM points
    WHERE datetime(created_at) >= datetime('now', '-{int(days)} days')
    GROUP BY phone
    ORDER BY s DESC
    LIMIT ?
    """, (limit,))
    pt_rows = cur.fetchall()

    conn.close()

    lines = [f"CON Weekly {ICON_STAR} ({days}d)"]

    lines.append("LM top3:")
    if lm_rows:
        for i, r in enumerate(lm_rows, start=1):
            lines.append(f"{i}) {r['village']} x{int(r['c'])}")
    else:
        lines.append("No landmarks yet.")

    lines.append("Helpers top3:")
    if pt_rows:
        for i, r in enumerate(pt_rows, start=1):
            lines.append(f"{i}) {display_name(r['phone'])} +{int(r['s'])}")
    else:
        lines.append("No points yet.")

    lines.append("0. Back")
    return "\n".join(lines)


# =========================
# CALLBACK REQUEST (future)
# =========================

def create_callback_request(session_id: str, customer_phone: str, target_phone: str, target_kind: str, village: str) -> None:
    conn = db()
    cur = conn.cursor()
    cur.execute("""
    INSERT INTO callback_requests (session_id, customer_phone, target_phone, target_kind, village, status, created_at)
    VALUES (?, ?, ?, ?, ?, 'NEW', datetime('now'))
    """, (session_id, normalize_phone(customer_phone), normalize_phone(target_phone), target_kind, village))
    conn.commit()
    conn.close()


# =========================
# FLOWS
# =========================

def get_customer_context(phone: str):
    """
    Return (village, landmark).

    New preferred source:
      - onboarding.user_prefs (role/area_type/landmark) in /opt/angelopp/data/bumala.db

    Old fallback (legacy tables):
      - kept only if it works; never crash.
    """
    # 1) Preferred: onboarding prefs (new flow)
    try:
        prefs = onboarding.get_prefs(phone)
        if prefs and prefs.get("landmark"):
            area = (prefs.get("area_type") or "village").strip().lower()
            # Keep legacy code expecting 'village' to be a village name
            village = "Bumala" if area == "village" else area.title()
            return village, prefs["landmark"]
    except Exception:
        pass

    # 2) Fallback: legacy logic (if present in DB) — but NEVER crash
    try:
        # If your codebase defines a db/connect helper, try to use it.
        if "get_db" in globals():
            conn = get_db()
        elif "db" in globals():
            conn = db()
        else:
            # Last resort: sqlite3 connect to the same DB path onboarding uses
            import sqlite3
            conn = sqlite3.connect(str(onboarding.DB_PATH))
        cur = conn.cursor()

        # Try common legacy tables/columns without assuming exact schema
        # First attempt: customer_locations(phone, village, landmark)
        try:
            cur.execute("SELECT village, landmark FROM customer_locations WHERE phone=? ORDER BY id DESC LIMIT 1", (phone,))
            row = cur.fetchone()
            if row and row[0] and row[1]:
                return row[0], row[1]
        except Exception:
            pass

        # Second attempt: landmarks(phone, village, name) or landmarks(added_by, village, name)
        try:
            cols = [r[1] for r in cur.execute("PRAGMA table_info(landmarks)").fetchall()]
            if "phone" in cols:
                cur.execute("SELECT village, name FROM landmarks WHERE phone=? ORDER BY id DESC LIMIT 1", (phone,))
                row = cur.fetchone()
                if row and row[0] and row[1]:
                    return row[0], row[1]
            elif "added_by" in cols:
                cur.execute("SELECT village, name FROM landmarks WHERE added_by=? ORDER BY id DESC LIMIT 1", (phone,))
                row = cur.fetchone()
                if row and row[0] and row[1]:
                    return row[0], row[1]
        except Exception:
            pass

    except Exception:
        pass

    # 3) Safe default
    return "Bumala", "Church"


def handle_find_rider(parts: List[str], session_id: str, phone: str) -> Tuple[str, int]:
    # Use customer's most recent context from DB
    village, landmark = get_customer_context(phone)

    # If we still don't know where the customer is, ask them to set it
    if not village and not landmark:
        return ussd_response(
            "\n".join([
                "CON Find a Rider",
                "We don't know your location yet.",
                "Please set it first:",
                "Menu > 5. Set my location",
                "0. Back",
            ])
        ), 200

    # Pilot default
    if not village and landmark:
        village = "Bumala"

    return ussd_response(nearest_drivers_screen(phone=phone, village=village, landmark=landmark)), 200


def handle_businesses(parts: List[str], session_id: str, phone: str) -> Tuple[str, int]:
    # parts[0] == "2"
    if len(parts) == 1:
        return ussd_response(village_menu("Businesses in which village?")), 200

    if parts[1] == "0":
        return ussd_response(main_menu()), 200

    village = village_key_to_name(parts[1])

    if len(parts) == 2:
        return ussd_response(category_menu(f"{village}: choose category")), 200

    if parts[2] == "0":
        return ussd_response(village_menu("Businesses in which village?")), 200

    category = category_key_to_name(parts[2])

    if len(parts) == 3:
        rows = list_businesses(village, category, limit=MAX_LIST)
        lines = [f"CON {category} ({village})"]
        if not rows:
            lines.append("No businesses yet.")
            lines.append("0. Back")
            return ussd_response("\n".join(lines)), 200

        for i, r in enumerate(rows, start=1):
            loc = (r["location"] or "").strip()
            loc_txt = f" - {loc}" if loc else ""
            lines.append(f"{i}. {r['name']}{loc_txt} {mask_phone(r['owner_phone'])}")
        lines.append("0. Back")
        return ussd_response("\n".join(lines)), 200

    # Optional: allow selection -> callback request (future)
    try:
        idx = int(parts[3])
    except Exception:
        return ussd_response("CON Invalid selection.\n0. Back"), 200

    rows = list_businesses(village, category, limit=MAX_LIST)
    if idx < 1 or idx > len(rows):
        return ussd_response("CON Invalid selection.\n0. Back"), 200

    target_phone = rows[idx - 1]["owner_phone"]
    create_callback_request(session_id, phone, target_phone, "business", village)

    return (
        "END Request saved.\n"
        "For safety: phone numbers stay hidden.\n"
        "Business owner/admin can call back."
    ), 200


def handle_register(parts: List[str], session_id: str, phone: str) -> Tuple[str, int]:
    # parts[0] == "3"
    if len(parts) == 1:
        return ussd_response("CON Register\n1. Rider\n2. Business\n0. Back"), 200

    if parts[1] == "0":
        return ussd_response(main_menu()), 200

    if parts[1] == "1":
        # Rider registration under 3*1*...
        return handle_register_rider(parts[1:], session_id, phone)
    if parts[1] == "2":
        # Business registration under 3*2*...
        return handle_register_business(parts[1:], session_id, phone)

    return ussd_response("CON Invalid.\n0. Back"), 200


def handle_register_rider(parts: List[str], session_id: str, phone: str) -> Tuple[str, int]:
    # parts[0] == "1" inside register
    # 3*1 -> ask village
    if len(parts) == 1:
        return ussd_response(village_menu("Register Rider: choose village")), 200

    if parts[1] == "0":
        return ussd_response("CON Register\n1. Rider\n2. Business\n0. Back"), 200

    village = village_key_to_name(parts[1])

    if len(parts) == 2:
        return ussd_response(rider_type_menu(f"{village}: rider type")), 200

    if parts[2] == "0":
        return ussd_response(village_menu("Register Rider: choose village")), 200

    rider_type = rider_type_key_to_name(parts[2])

    if len(parts) == 3:
        return ussd_response("CON Rider name?"), 200

    name = (parts[3] or "").strip()
    if not name:
        return ussd_response("CON Please enter a name."), 200

    if len(parts) == 4:
        return ussd_response("CON SACCO name? (or 0 to skip)"), 200

    sacco = (parts[4] or "").strip()
    if sacco == "0":
        sacco = ""

    if len(parts) == 5:
        return ussd_response("CON Location / landmark? (e.g. Market gate)"), 200

    location = (parts[5] or "").strip()

    upsert_rider(
        phone=normalize_phone(phone),
        name=name,
        village=village,
        rider_type=rider_type,
        sacco=sacco,
        location=location,
    )

    return (
        f"END Rider registered {ICON_DONE}\n"
        f"{name} ({rider_type})\n"
        f"{village}"
    ), 200


def handle_register_business(parts: List[str], session_id: str, phone: str) -> Tuple[str, int]:
    # parts[0] == "2" inside register
    if len(parts) == 1:
        return ussd_response(village_menu("Register Business: choose village")), 200

    if parts[1] == "0":
        return ussd_response("CON Register\n1. Rider\n2. Business\n0. Back"), 200

    village = village_key_to_name(parts[1])

    if len(parts) == 2:
        return ussd_response(category_menu(f"{village}: business category")), 200

    if parts[2] == "0":
        return ussd_response(village_menu("Register Business: choose village")), 200

    category = category_key_to_name(parts[2])

    if len(parts) == 3:
        return ussd_response("CON Business name?"), 200

    name = (parts[3] or "").strip()
    if not name:
        return ussd_response("CON Please enter business name."), 200

    if len(parts) == 4:
        return ussd_response("CON Location / landmark? (or 0 to skip)"), 200

    location = (parts[4] or "").strip()
    if location == "0":
        location = ""

    insert_business(
        owner_phone=normalize_phone(phone),
        name=name,
        category=category,
        village=village,
        location=location,
    )

    return (
        f"END Business registered {ICON_DONE}\n"
        f"{name}\n"
        f"{category} - {village}"
    ), 200


def handle_set_location(parts: List[str], session_id: str, phone: str) -> Tuple[str, int]:
    """
    Simple 2-step picker:
      5                -> choose village
      5*<village>      -> choose landmark in that village
      5*<village>*<lm> -> save location (insert landmark entry for this phone)
    """
    # parts like ["5", ...]
    step = len(parts)

    # STEP 1: choose village
    if step == 1:
        # If you have a villages table later: switch to DB query.
        villages = ["Bumala"]
        lines = ["CON Set my location", "Choose your village:"]
        for i, v in enumerate(villages, 1):
            lines.append(f"{i}. {v}")
        lines.append("0. Back")
        return ussd_response("\n".join(lines)), 200

    # interpret selection village
    if step == 2:
        sel = parts[1].strip()
        village = "Bumala"
        if sel == "0":
            return ussd_response(main_menu()), 200
        if sel == "1":
            village = "Bumala"
        else:
            # allow direct village input too
            village = sel

        # show existing landmarks for that village + option to add new
        conn = db()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT name FROM landmarks WHERE village = ? AND name IS NOT NULL AND name != '' GROUP BY name ORDER BY name ASC LIMIT 20",
                (village,),
            )
            rows = cur.fetchall() or []
        finally:
            try: conn.close()
            except Exception: pass

        lines = [f"CON Location: {village}", "Choose landmark:"]
        idx = 1
        for r in rows:
            lines.append(f"{idx}. {r[0]}")
            idx += 1
        lines.append(f"{idx}. Add new landmark")
        lines.append("0. Back")
        return ussd_response("\n".join(lines)), 200

    # STEP 3: choose landmark or add new
    if step == 3:
        sel = parts[2].strip()
        # resolve village again
        village_sel = parts[1].strip()
        village = "Bumala" if village_sel in ("1", "", None) else village_sel
        if village_sel == "1":
            village = "Bumala"

        if sel == "0":
            return ussd_response(main_menu()), 200

        # fetch list again (same as step 2) so numbering matches
        conn = db()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT name FROM landmarks WHERE village = ? AND name IS NOT NULL AND name != '' GROUP BY name ORDER BY name ASC LIMIT 20",
                (village,),
            )
            rows = cur.fetchall() or []
        finally:
            try: conn.close()
            except Exception: pass

        add_new_index = len(rows) + 1

        # If they chose "Add new landmark"
        if sel == str(add_new_index):
            return ussd_response(
                "\n".join([
                    f"CON New landmark for {village}",
                    "Type the landmark name:",
                    "0. Back",
                ])
            ), 200

        # Otherwise they chose an existing landmark
        try:
            n = int(sel)
            if 1 <= n <= len(rows):
                landmark = rows[n-1][0]
            else:
                landmark = None
        except ValueError:
            # allow direct landmark text too
            landmark = sel

        if not landmark:
            return ussd_response("CON Invalid choice\n0. Back"), 200

        # Save: create/overwrite a landmark entry for this phone
        # We'll insert into landmarks with (phone, village, name, description)
        conn = db()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO landmarks (phone, village, name, description, created_at)
                VALUES (?, ?, ?, ?, datetime('now'))
                """,
                (phone, village, landmark, "Set via menu"),
            )
            conn.commit()
        finally:
            try: conn.close()
            except Exception: pass

        return ussd_response(
            "\n".join([
                "CON Location saved ✓",
                f"Village: {village}",
                f"Landmark: {landmark}",
                "0. Back",
            ])
        ), 200

    # STEP 4: they typed a new landmark name after choosing "Add new"
    if step >= 4:
        village_sel = parts[1].strip()
        village = "Bumala" if village_sel == "1" else village_sel
        # parts[2] was "Add new landmark" selection, parts[3] is typed name
        landmark = parts[3].strip() if len(parts) >= 4 else ""
        if not landmark or landmark == "0":
            return ussd_response(main_menu()), 200

        conn = db()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO landmarks (phone, village, name, description, created_at)
                VALUES (?, ?, ?, ?, datetime('now'))
                """,
                (phone, village, landmark, "Added via Set my location"),
            )
            conn.commit()
        finally:
            try: conn.close()
            except Exception: pass

        return ussd_response(
            "\n".join([
                "CON Location saved ✓",
                f"Village: {village}",
                f"Landmark: {landmark}",
                "0. Back",
            ])
        ), 200


def handle_challenge(parts: list[str], session_id: str, phone: str):
    # parts: ["4"] / ["4","1"] / ["4","2"] / ["4","3",name,desc]
    ensure_challenge_schema()

    if len(parts) == 1:
        return ussd_response(
            "CON Today’s Challenge\n"
            "1. Claim ✓\n"
            "2. Weekly Leaderboard ★\n"
            "3. Add Landmark\n"
            "0. Back"
        ), 200

    if parts[1] == "0":
        return ussd_response(main_menu()), 200

    # 4*1 daily claim (+1)
    if parts[1] == "1":
        if _mark_claim_today(phone):
            _add_points(phone, 1, "daily_claim")
            return (
                "END Challenge claimed ✓\n"
                "+1 point\n"
                "(Tip: Add 1 useful landmark today)",
                200
            )
        return ("END Already claimed today ✓\n(Try again tomorrow)", 200)

    # 4*2 weekly leaderboard
    if parts[1] == "2":
        return ussd_response(weekly_leaderboard(days=7, limit=3)), 200

    # 4*3 add landmark flow
    if parts[1] == "3":
        if len(parts) == 2:
            return ussd_response(
                "CON Add a Landmark\n"
                "Type a short name:\n"
                "(e.g. Market Gate, Water Pump)\n"
                "0. Back"
            ), 200

        if len(parts) == 3:
            if parts[2] == "0":
                return ussd_response(main_menu()), 200
            name = _clean_text(parts[2], 28)
            if not name:
                return ussd_response("CON Name too short.\n0. Back"), 200
            return ussd_response(
                "CON Describe the place shortly:\n"
                "(e.g. Main entrance near boda stage)\n"
                f"Name: {name}\n"
                "0. Back"
            ), 200

        if len(parts) >= 4:
            if parts[3] == "0":
                return ussd_response(main_menu()), 200

            if _added_landmark_today(phone):
                return ("END Already added a landmark today ✓\n(Try again tomorrow)", 200)

            name = _clean_text(parts[2], 28)
            desc = _clean_text(parts[3], 60)

            if not name or len(name) < 3:
                return ussd_response("CON Invalid name.\n0. Back"), 200
            if not desc or len(desc) < 6:
                return ussd_response("CON Description too short.\n0. Back"), 200

            _save_landmark(phone, "Bumala", name, desc)
            _add_points(phone, 3, "landmark_add")
            return ("END Landmark saved ✓\nThank you for helping Bumala\n+3 points", 200)

    return ussd_response("CON Invalid option.\n0. Back"), 200


def nearest_drivers_screen(phone: str, village: str, landmark: str, limit: int = 3) -> str:
    drivers = get_nearest_drivers(phone=phone, village=village, landmark=landmark, limit=limit)

    score_by_phone = {}
    try:
        tmp = []
        for r in drivers:
            phone_ = ""
            eta_ = 999
            lm_ = ""

            # 1) PersonLocation-like objects (has .phone / .eta_minutes / .landmark)
            if hasattr(r, "phone") or hasattr(r, "eta_minutes"):
                phone_ = getattr(r, "phone", "") or ""
                eta_ = getattr(r, "eta_minutes", 999)
                lm_ = getattr(r, "landmark", "") or ""

            # 2) tuples/lists
            elif isinstance(r, (list, tuple)):
                phone_ = r[0] if len(r) > 0 else ""
                eta_   = r[1] if len(r) > 1 else 999
                lm_    = r[2] if len(r) > 2 else ""

            # 3) dicts
            elif isinstance(r, dict):
                phone_ = r.get("phone", "")
                eta_   = r.get("eta_minutes", r.get("eta", 999))
                lm_    = r.get("landmark", "") or ""

            # 4) unknown
            else:
                phone_, eta_, lm_ = str(r), 999, ""

            # DEMO inputs (so you SEE reordering) — replace later with real trust/fairness
            digits = "".join(ch for ch in str(phone_) if ch.isdigit())
            last = int(digits[-1]) if digits else 0
            trust = 0.50
            recent = 1
            if last == 3:
                trust, recent = 0.95, 0
            elif last == 2:
                trust, recent = 0.25, 3
            elif last == 4:
                trust, recent = 0.60, 1

            d = {
                "phone": phone_,
                "eta_minutes": float(eta_ if eta_ is not None else 999),
                "landmark": lm_ or "",
                "trust_score": float(trust),
                "recent_jobs": int(recent),
                "expected_income": 0.0,
                "_raw": r,
            }
            tmp.append(d)

        tmp = _rank_riders_if_possible(tmp)

        ranked_drivers = []
        for d in tmp:
            ph = d.get("phone", "")
            ranked_drivers.append((ph, int(d.get("eta_minutes", 999)), d.get("landmark", "")))

            try:
                score_by_phone[ph] = explain_score(Candidate(
                    phone=ph,
                    eta_minutes=float(d.get("eta_minutes", 999)),
                    trust_score=float(d.get("trust_score", 0.5)),
                    recent_jobs=int(d.get("recent_jobs", 0)),
                    expected_income=float(d.get("expected_income", 0)),
                ))
            except Exception:
                pass

        drivers = ranked_drivers

    except Exception:
        score_by_phone = {}

    lines = ["CON Nearest riders"]
    i = 1
    for (ph, eta, lm) in drivers:
        suffix = ""
        if ph in score_by_phone and score_by_phone[ph]:
            suffix = " [" + score_by_phone[ph] + "]"
        lines.append(f"{i}) {ph} ~{eta} min ({lm or 'Unknown'}){suffix}")
        i += 1
    lines.append("0. Back")
    return "\n".join(lines)

def handle_ussd_core(session_id: str, phone_number: str, text: str) -> Tuple[str, int]:
    """
    Africa's Talking POST form fields:
      sessionId, phoneNumber, text
    Must return (body, http_code).
    Body MUST start with CON or END.
    """
    ensure_schema()

    phone = normalize_phone(phone_number)
    parts = parse_text(text)

    # CHANGE_PLACE_ROUTER_V3 (override buggy older place logic)
    if parts and parts[0] == "4":
        return handle_change_place_v3(parts, phone)

    # --- CHANGE_PLACE_VILLAGE_PICK_V2: handle 4*1*<village> ---
    if parts and parts[0] == "4" and len(parts) >= 2 and parts[1] == "1":
        # 4*1 -> show village list (existing)
        if len(parts) == 3:
            choice = parts[2]
            villages = {"1": "Bumala", "2": "Butula", "3": "Busia"}
            v = villages.get(choice)
            if not v:
                return ussd_response("CON Invalid village.\n0. Back"), 200
        # Minimal working: confirm (later you can persist into user prefs)
        # PERSIST_VILLAGE_V1: store village in user prefs
        try:
            conn = db()
            cur = conn.cursor()
            # ensure prefs row exists
            ensure_user_prefs(conn)
            cur.execute("UPDATE user_prefs SET village=? WHERE phone=?", (v, phone))
            conn.commit()
        except Exception:
            pass
            return ussd_response(f"CON Location set ✓\nVillage: {v}\n0. Back"), 200
    # --- END CHANGE_PLACE_VILLAGE_PICK_V2 ---

    # --- CHANGE_PLACE_ROUTER_V2: ensure 'Change my place' has priority (fixes 4*1 accidentally triggering challenge) ---
    if parts and parts[0] == "4":
        if len(parts) == 1:
            return ussd_response(
                "CON Choose your area:\n"
                "1. Village\n"
                "2. Town/City\n"
                "3. Airport\n"
                "0. Back"
            ), 200

        if len(parts) >= 2 and parts[1] == "0":
            return ussd_response(root_menu(phone)), 200

        # 4*1 -> Village selector (uses village_menu() if you have it)
        if parts[1] == "1":
            try:
                return ussd_response(village_menu()), 200
            except Exception:
                return ussd_response(
                    "CON Choose your village:\n"
                    "1. Bumala\n"
                    "2. Butula\n"
                    "3. Busia\n"
                    "0. Back"
                ), 200

        if parts[1] == "2":
            return ussd_response("CON Town/City (soon)\n0. Back"), 200

        if parts[1] == "3":
            return ussd_response("CON Airport (soon)\n0. Back"), 200

        return ussd_response("CON Invalid option.\n0. Back"), 200
    # --- END CHANGE_PLACE_ROUTER_V2 ---
    # --- BUSINESSES_V2_ROUTER_V1 (robust) ---
    if parts and parts[0] == "2":
        return handle_businesses_v2(parts, session_id, phone), 200
    # --- END BUSINESSES_V2_ROUTER_V1 ---

    # --- BUSINESSES_VILLAGE_INTERCEPT_V1 ---
    # When user selects Local Businesses -> village (2*1 etc),
    # map numeric choice to a village name string early to avoid crashes.
    if parts and parts[0] == "2" and len(parts) >= 2:
        if parts[1] == "0":
            return ussd_response(root_menu(phone)), 200
        _vn = village_name_from_choice(parts[1])
        if _vn:
            parts[1] = _vn
    # --- END BUSINESSES_VILLAGE_INTERCEPT_V1 ---


    # --- TRAVEL (customer submenu) ---
    if parts and parts[0] == '8':
        return handle_travel(parts, session_id, phone)


    # --- TRAVEL INTERCEPT (customer option 8) ---
    try:
        role = get_user_role(phone_number)
    except Exception:
        role = "Customer"

    if parts and parts[0] == "8" and role == "Customer":
        return ussd_response(handle_travel(parts, session_id, phone_number)), 200
    # -------------------------------------------


    # --- CUSTOMER TRAVEL (submenu) ---
    try:
        role = get_user_role(phone_number)
    except Exception:
        role = "Customer"
    if parts and parts[0] == "8" and role == "Customer":
        return ussd_response(handle_travel(parts, session_id, phone_number)), 200
    # ---------------------------------


    # --- ROLE SWITCH (early intercept) ---
    if parts and parts[0] == '9':
        return handle_role_switch(parts, phone)

    # --- PROVIDER ROOT OVERRIDE ---
    if not parts:
        try:
            role = get_user_role(phone)
        except Exception:
            role = 'customer'
        if role == 'provider':
            return ussd_response('CON Bumala Directory\\n1. Find a Rider ->\\n2. Local Businesses\\n3. Register (Rider / Business)\\n4. Today’s Challenge *\\n5. Set my location\\n0. Exit'), 200

    # empty -> show main menu
    if not parts:
        return ussd_response(root_menu(phone)), 200

    # Global "0" behavior:
    # - if user sends "0" at root: exit
    # - in submenus we handle 0 locally, but this catches pure "0"
    if parts == ["0"]:
        return "END Bye.", 200

    # Root routing
    root = (parts[0].strip() if parts else "")

    # Backward compatibility: old menu used 6 for challenge
    if root == "6":
        root = "4"

    if root == "":
        return ussd_response(root_menu(phone)), 200

    if root == "1":
        return handle_find_rider(parts, session_id, phone)

    if root == "2":
        return handle_businesses(parts, session_id, phone)

    if root == "3":
        return handle_register(parts, session_id, phone)

    if root == "4":
        return handle_challenge(parts, session_id, phone)

    if root == "5":

        return handle_set_location(parts, session_id, phone)

        return "END Bye.", 200

    return ussd_response(main_menu(phone) + "\n\nInvalid option."), 200

# =========================================================
# Relative distance integration
# =========================================================

def get_nearest_drivers(phone: str, village: str, landmark: str | None = None, limit: int = 3):
    """
    Returns nearest drivers based on relative distance logic
    """

    customer = PersonLocation(
        phone=phone,
        village=village,
        landmark=landmark
    )

    # TODO: replace with real DB query
    drivers = [
        PersonLocation(phone="+254700000002", village=village, landmark="Market Gate", eta_minutes=2),
        PersonLocation(phone="+254700000003", village=village, landmark="Water Pump", eta_minutes=5),
        PersonLocation(phone="+254700000004", village="Busia", landmark=None, eta_minutes=15),
    ]

    ranked = rank_drivers(customer, drivers)
    return ranked[:limit]



# =========================================================
# Channels — MVP handlers (Listen + My channel)
# Menu uses options 6 and 7 in Role Home to avoid breaking core routes.
# =========================================================

CHANNEL_CATEGORIES = ["Community", "Business", "Sacco", "Education", "Entertainment"]

def _db():
    # Always use the same DB as onboarding (this VPS uses /opt/angelopp/app/bumala.db)
    return sqlite3.connect(str(onboarding.DB_PATH))

def get_my_channel(phone: str):
    conn = _db()
    cur = conn.cursor()
    cur.execute("SELECT id, name, category FROM channels WHERE owner_phone=? AND is_active=1 ORDER BY id DESC LIMIT 1", (phone,))
    row = cur.fetchone()
    conn.close()
    return row  # (id, name, category) or None

def can_post_today(channel_id: int) -> bool:
    conn = _db()
    cur = conn.cursor()
    cur.execute("""
        SELECT COUNT(*) FROM channel_messages
        WHERE channel_id=? AND date(created_at)=date('now','localtime')
    """, (channel_id,))
    n = int(cur.fetchone()[0] or 0)
    conn.close()
    return n < 1  # MVP: max 1 message per day

def create_channel(phone: str, name: str, category: str) -> int:
    name = (name or "").strip()
    if len(name) > 24:
        name = name[:24]
    if not name:
        name = "My Channel"
    if category not in CHANNEL_CATEGORIES:
        category = "Community"

    conn = _db()
    cur = conn.cursor()
    cur.execute("INSERT INTO channels(owner_phone,name,category) VALUES(?,?,?)", (phone, name, category))
    cid = cur.lastrowid
    conn.commit()
    conn.close()
    return int(cid)

def post_message(channel_id: int, text: str) -> int:
    text = (text or "").strip()
    if len(text) > 240:
        text = text[:240]
    conn = _db()
    cur = conn.cursor()
    cur.execute("INSERT INTO channel_messages(channel_id,text) VALUES(?,?)", (channel_id, text))
    mid = cur.lastrowid
    conn.commit()
    conn.close()
    return int(mid)


def get_latest_messages(category: str, limit: int = 5):
    """
    Returns list of tuples: (channel_name, text, created_at)
    Never throws (callers may still wrap).
    """
    try:
        conn = db()
        ensure_messages(conn)
        cur = conn.cursor()

        # Try to join with channels if that table exists
        try:
            cur.execute("""
                SELECT c.name AS channel_name,
                       m.text AS text,
                       m.created_at AS created_at
                FROM messages m
                LEFT JOIN channels c ON c.id = m.channel_id
                WHERE lower(trim(m.category)) = lower(trim(?))
                ORDER BY m.id DESC
                LIMIT ?
            """, (category, int(limit)))
            rows = cur.fetchall() or []
            out = []
            for r in rows:
                # sqlite3.Row or tuple
                chname = (r["channel_name"] if hasattr(r, "__getitem__") else r[0]) or "Channel"
                text   = (r["text"] if hasattr(r, "__getitem__") else r[1]) or ""
                ts     = (r["created_at"] if hasattr(r, "__getitem__") else r[2]) if len(r) > 2 else ""
                out.append((str(chname), str(text), str(ts or "")))
            return out
        except Exception:
            # Fallback: no channels table or join failed
            cur.execute("""
                SELECT category, text, created_at
                FROM messages
                WHERE lower(trim(category)) = lower(trim(?))
                ORDER BY id DESC
                LIMIT ?
            """, (category, int(limit)))
            rows = cur.fetchall() or []
            out = []
            for r in rows:
                cat  = (r["category"] if hasattr(r, "__getitem__") else r[0]) or "Category"
                text = (r["text"] if hasattr(r, "__getitem__") else r[1]) or ""
                ts   = (r["created_at"] if hasattr(r, "__getitem__") else r[2]) if len(r) > 2 else ""
                out.append((str(cat), str(text), str(ts or "")))
            return out
    except Exception:
        return []


def handle_sacco_updates(raw: str, phone: str):
    """
    Sacco Line navigation:
      5        -> dashboard
      5*1      -> latest sacco updates (placeholder; can be linked to Sacco channel posts)
      5*2      -> principles/safety
      5*3      -> verified riders (placeholder list)
      5*4      -> report issue (collect text)
      5*5      -> sacco role in community
      5*0      -> back
    Returns:
      - string (USSD body)
      - or None for "back to root"
    """
    raw = (raw or "").strip()
    parts = raw.split("*") if raw else []

    if raw == "5":
        return (
            "CON Sacco Line\n"
            "1. Latest Sacco updates\n"
            "2. Sacco principles & safety\n"
            "3. Verified riders\n"
            "4. Report an issue\n"
            "5. How Sacco supports the community\n"
            "0. Back"
        )

    if raw == "5*1":
        return (
            "CON Sacco — latest\n"
            "No updates yet.\n\n"
            "Tip: Sacco leaders can post updates\n"
            "via a Sacco channel.\n"
            "0. Back"
        )

    if raw == "5*2":
        return (
            "CON Sacco principles\n"
            "• Safety first — people before profit\n"
            "• Respect customers & community\n"
            "• Fair pricing, no exploitation\n"
            "• Care for children & school zones\n"
            "• Help each other in emergencies\n\n"
            "These principles guide all Sacco riders.\n"
            "0. Back"
        )

    if raw == "5*3":
        # Placeholder: later you can pull from DB "providers" flagged verified_by_sacco=1
        return (
            "CON Verified riders\n"
            "1. +254700000002 (Bumala Sacco)\n"
            "2. +254700000005 (Market Route)\n\n"
            "Verified by local Sacco leadership.\n"
            "0. Back"
        )

    if raw.startswith("5*4"):
        # 5*4 -> prompt, 5*4*<text> -> accept
        if len(parts) == 2:
            return "CON Report issue\nType your issue (max 200 chars):"
        issue = "*".join(parts[2:]).strip()
        if not issue:
            return "CON Report issue\nType your issue (max 200 chars):"
        issue = issue[:200]

        # Minimal safe storage hook: if you already have a table, you can insert here.
        # For now: do nothing (or log) to keep USSD stable.
        try:
            if "db" in globals():
                conn = db()
                cur = conn.cursor()
                # create table if it doesn't exist (lightweight)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS sacco_issues (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        phone TEXT NOT NULL,
                        issue TEXT NOT NULL,
                        created_at TEXT NOT NULL DEFAULT (datetime('now'))
                    )
                """)
                cur.execute("INSERT INTO sacco_issues(phone, issue) VALUES(?,?)", (phone, issue))
                conn.commit()
        except Exception:
            pass

        return (
            "CON Reported ✓\n"
            "Your issue is shared with the Sacco.\n"
            "Thank you for helping improve safety.\n"
            "0. Back"
        )

    if raw == "5*5":
        return (
            "CON Sacco & community\n"
            "• Shares safety knowledge\n"
            "• Verifies trusted riders\n"
            "• Helps resolve conflicts\n"
            "• Supports fair income\n"
            "• Builds local trust\n\n"
            "Angelopp works WITH Sacco,\n"
            "not above it.\n"
            "0. Back"
        )

    if raw == "5*0":
        return None

    return "CON Sacco Line\nInvalid option.\n0. Back"

def handle_sacco_line(raw: str, phone: str) -> str:
    """
    Sacco Line: coordination + trust layer for sacco's.
    Uses existing channel_messages via get_latest_messages("Sacco").
    Never throws (USSD must not 500).
    """
    parts = (raw or "").split("*")

    if raw == "5":
        return "\n".join([
            "CON Sacco Line",
            "1. Latest Sacco updates",
            "2. How Sacco grows with Angelopp",
            "3. Verified riders (soon)",
            "4. Report issue (soon)",
            "0. Back",
        ])

    # back
    if len(parts) >= 2 and parts[1] == "0":
        return "CON Back\n0. Back"

    # latest updates
    if len(parts) >= 2 and parts[1] == "1":
        try:
            rows = get_latest_messages("Sacco", limit=5)
        except Exception:
            rows = []
        lines = ["CON Sacco — latest"]
        if not rows:
            lines.append("No updates yet.")
        else:
            for i, (chname, msg, _) in enumerate(rows, start=1):
                txt = (msg or "").replace("\n"," ")
                if len(txt) > 80:
                    txt = txt[:80] + "…"
                lines.append(f"{i}. {chname}: {txt}")
        lines.append("0. Back")
        return "\n".join(lines)

    # explainer
    if len(parts) >= 2 and parts[1] == "2":
        return "\n".join([
            "CON Sacco power",
            "• Official Sacco channel for safety rules",
            "• Verified riders list + ID checks",
            "• Announce procedures + dispute handling",
            "• Community trust + stable income",
            "",
            "Tip: create a channel in category 'Sacco'",
            "then post updates for everyone.",
            "0. Back",
        ])

    return "CON Sacco Line\nInvalid option.\n0. Back"

def handle_listen_channels(raw: str) -> str:
    parts = (raw or "").split("*")

    # raw == "6" -> show categories
    if raw == "6":
        lines = ["Listen (channels)"]
        for i, cat in enumerate(CHANNEL_CATEGORIES, start=1):
            lines.append(f"{i}. {cat}")
        lines.append("0. Back")
        return "CON " + "\n".join(lines)

    # raw like "6*1" -> list latest messages
    if len(parts) >= 2 and parts[0] == "6":
        choice = parts[1].strip()
        if choice == "0":
            return "CON Back\n0. Back"
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(CHANNEL_CATEGORIES):
                cat = CHANNEL_CATEGORIES[idx]
                # LISTEN_SAFE_V2: guard DB access so USSD never 500s
                try:
                    _rows = get_latest_messages(cat, limit=5)
                except Exception:
                    _rows = []
                rows = _rows
    # rows already set by LISTEN_SAFE_V2
                lines = [f"{cat} — latest"]
                if not rows:
                    lines.append("No messages yet.")
                else:
                    for k, (name, text, _) in enumerate(rows, start=1):
                        txt = (text or "").replace("\n", " ")
                        if len(txt) > 60:
                            txt = txt[:60] + "…"
                        lines.append(f"{k}. {name}: {txt}")
                lines.append("0. Back")
                return "CON " + "\n".join(lines)

    return "CON Listen\n0. Back"

def handle_my_channel(raw: str, phone: str) -> str:
    parts = (raw or "").split("*")
    # raw == "7" -> show dashboard or create prompt
    if raw == "7":
        ch = get_my_channel(phone)
        if not ch:
            return "CON My channel\nYou don’t have a channel yet.\n1. Create my channel\n0. Back"
        cid, name, cat = ch
        return (
            "CON My channel: " + name + "\n"
            "1. Post message\n"
            "2. View last message\n"
            "3. Rename channel\n"
            "0. Back"
        )

    # If no channel yet and user selects create
    if parts[0] == "7":
        ch = get_my_channel(phone)

        # Create flow:
        # 7*1 -> ask name
        if len(parts) == 2 and parts[1] == "1" and not ch:
            return "CON Create channel\nType a name:"

        # 7*1*<name> -> choose category
        if len(parts) == 3 and parts[1] == "1" and not ch:
            name = parts[2]
            lines = ["CON Choose category:"]
            for i, cat in enumerate(CHANNEL_CATEGORIES, start=1):
                lines.append(f"{i}. {cat}")
            lines.append("0. Cancel")
            return "\n".join(lines)

        # 7*1*<name>*<cat> -> create
        if len(parts) >= 4 and parts[1] == "1" and not ch:
            name = parts[2]
            c = parts[3].strip()
            if c == "0":
                return "CON Cancelled\n0. Back"
            if c.isdigit():
                idx = int(c) - 1
                cat = CHANNEL_CATEGORIES[idx] if 0 <= idx < len(CHANNEL_CATEGORIES) else "Community"
                cid = create_channel(phone, name, cat)
                return f"CON Channel created ✓\nName: {name[:24]}\nCategory: {cat}\n0. Back"

        # Existing channel actions
        if ch:
            cid, name, cat = ch

            # Post message:
            # 7*1 -> ask text
            if len(parts) == 2 and parts[1] == "1":
                if not can_post_today(cid):
                    return "CON Limit reached\nYou can post 1 message/day.\n0. Back"
                return "CON Post message (max 240 chars):"


        # POST_MESSAGE_V1:
        # 7*1*<text> -> save message to DB (never 500)
        if len(parts) >= 3 and parts[1] == "1" and ch:
            msg = "*".join(parts[2:]).strip()
            if not msg:
                return "CON Empty message.\n0. Back"
            if len(msg) > 240:
                msg = msg[:240]

            try:
                cid, cname, ccat = ch  # from get_my_channel()
                conn = db()
                ensure_messages(conn)
                cur = conn.cursor()
                cur.execute(
                    "INSERT INTO messages(channel_id, category, author_phone, text) VALUES (?,?,?,?)",
                    (int(cid), str(ccat or ""), str(phone or ""), str(msg))
                )
                conn.commit()
                return "CON Posted ✓\n0. Back"
            except Exception:
                return "CON Could not post now.\n0. Back"

            # 7*1*<text> -> save
            if len(parts) >= 3 and parts[1] == "1":
                if not can_post_today(cid):
                    return "CON Limit reached\nYou can post 1 message/day.\n0. Back"
                text = "*".join(parts[2:])  # keep '*' typed content
                post_message(cid, text)
                return "CON Posted ✓\n0. Back"

            # View last:
            if len(parts) == 2 and parts[1] == "2":
                conn = _db()
                cur = conn.cursor()
                cur.execute("SELECT text, created_at FROM channel_messages WHERE channel_id=? ORDER BY id DESC LIMIT 1", (cid,))
                row = cur.fetchone()
                conn.close()
                if not row:
                    return "CON No messages yet.\n0. Back"
                text, ts = row
                text = (text or "").replace("\n", " ")
                return f"CON Last message:\n{text}\n0. Back"

            # Rename:
            # 7*3 -> ask new name
            if len(parts) == 2 and parts[1] == "3":
                return "CON Rename channel\nType new name:"

            # 7*3*<newname> -> save
            if len(parts) >= 3 and parts[1] == "3":
                newname = parts[2].strip()[:24] or "My Channel"
                conn = _db()
                cur = conn.cursor()
                cur.execute("UPDATE channels SET name=? WHERE id=?", (newname, cid))
                conn.commit()
                conn.close()
                return f"CON Renamed ✓\nNew name: {newname}\n0. Back"

    return "CON My channel\n0. Back"

# -----------------------------
# New handle_ussd: onboarding gate first, then existing logic
# -----------------------------
def handle_ussd(session_id: str, phone_number: str, text: str):
    phone = (phone_number or "").strip()
    raw = (text or "").strip()

    

    # BIZ_BACK_TO_ROOT_V1: ensure businesses back-to-root never hits legacy directory
    if raw == "2*0":
        try:
            return handle_ussd(session_id=session_id, phone_number=phone_number, text="")
        except Exception:
            # last resort: behave like top-level root
            return handle_ussd(session_id=session_id, phone_number=phone_number, text="")
# 1) If onboarding not complete, return onboarding screens
    resp = onboarding.onboarding_response(session_id=session_id, phone=phone, text=raw)
    if resp is not None:
        return (resp, 200)

    # 2) Onboarded: show new "Role Home" when user starts (empty text)
    try:
        prefs = onboarding.get_prefs(phone)
    except Exception:
        prefs = {"role": "customer", "area_type": "village", "landmark": "Church"}

    role = (prefs.get("role") or "customer").strip().lower()
    area = (prefs.get("area_type") or "village").strip()
    village = get_pref_village(phone, fallback="Church")
    landmark = (prefs.get("landmark") or "").strip()
    # Exit if user explicitly chooses 0 at top-level
    last = raw.split("*")[-1] if raw else ""

    if raw == "":
        title = "Customer" if role == "customer" else "Service Provider"
        menu = f"""{title} (village: {village})
1. Find a Rider ->
2. Local Businesses
3. Register (Rider / Business)
4. Change my place
5. Sacco Line ->
6. Listen (channels)
7. My channel
8. Travel ->
9. Switch role
0. Exit"""
        return ("CON " + menu, 200)

    # Intercepts (before core)

    # Channels (6/7) — handled here so core routes remain unchanged
    # Listen (channels)
    # Sacco Line (option 5)
    # Sacco Line (option 5) — handled here so core remains unchanged
    if raw == "5" or raw.startswith("5*"):
        # Back-to-root behavior: 5*0 should return the real root (text="")
        if raw == "5*0" or raw.startswith("5*0*"):
            return handle_ussd(session_id=session_id, phone_number=phone, text="")
        return (handle_sacco_updates(raw, phone), 200)

    if raw == "6" or raw.startswith("6*"):
        return (handle_listen_channels(raw), 200)

    # My channel
    if raw == "7" or raw.startswith("7*"):
        return (handle_my_channel(raw, phone), 200)

    # BUSINESSES_ROUTER_V3: force businesses flow through handle_businesses_v2 (never 500)
    if raw == "2" or raw.startswith("2*"):
        parts = (raw or "").split("*")
        return (handle_businesses_v2(parts, session_id=session_id, phone=phone), 200)

    if last == "0":
        return ("END Bye.", 200)

    if last == "4":
        # Keep role, reset place => onboarding will ask area/landmark again
        try:
            onboarding.clear_location(phone)
        except Exception:
            pass
        # Ask area again
        r2 = onboarding.onboarding_response(session_id=session_id, phone=phone, text="")
        return ((r2 or """CON Choose your area:
1. Village
2. Town/City
3. Airport
0. Back"""), 200)

    if last == "9":
        # Reset everything => onboarding will ask role again
        try:
            onboarding.clear_role(phone)
        except Exception:
            pass
        r2 = onboarding.onboarding_response(session_id=session_id, phone=phone, text="")
        return ((r2 or """CON Angelopp
1. I am a Customer
2. I am a Service Provider
0. Exit"""), 200)

    # 3) Otherwise: run the original logic
    return handle_ussd_core(session_id=session_id, phone_number=phone_number, text=raw)


# ============================================================
# Travel (customer submenu) - placeholder flow
# ============================================================
def handle_travel(parts, session_id: str, phone: str):
    """
    Travel submenu (Customer).
    Uses ussd_response() so output is always CON/END compatible with Africa's Talking.
    Flow:
      8               -> menu
      8*0             -> back to root
      8*1             -> Plan a trip (asks From)
      8*1*<FROM>      -> asks To
      8*1*<FROM>*<TO> -> shows summary (placeholder)
      8*2             -> Find transport (placeholder)
      8*3             -> My trips (placeholder)
    """
    def _resp(body: str):
        # Prefer the project's wrapper (adds CON/END, etc.)
        if "ussd_response" in globals():
            return ussd_response(body), 200
        # Fallback (shouldn't happen in your project)
        body = body.strip("\n")
        if not (body.startswith("CON ") or body.startswith("END ")):
            body = "CON " + body
        return body, 200

    # 8 -> show menu
    if len(parts) == 1:
        return _resp(
            "Travel\n"
            "1. Plan a trip\n"
            "2. Find transport\n"
            "3. My trips (soon)\n"
            "0. Back"
        )

    choice = parts[1]

    # Back -> root menu (role-aware root will be applied there)
    if choice == "0":
        if "handle_ussd_core" in globals():
            return handle_ussd_core(session_id=session_id, phone_number=phone, text="")
        return _resp("Back\n0. Exit")

    # 1) Plan a trip (simple wizard)
    if choice == "1":
        if len(parts) == 2:
            return _resp("Plan a trip\nFrom (type a place):\n0. Back")
        if len(parts) == 3:
            frm = parts[2].strip()[:32]
            return _resp(f"Plan a trip\nFrom: {frm}\nTo (type a place):\n0. Back")
        if len(parts) >= 4:
            frm = parts[2].strip()[:32]
            to = parts[3].strip()[:32]
            return _resp(
                "Trip draft\n"
                f"From: {frm}\n"
                f"To: {to}\n"
                "Next: we can add date/time + budget + save it.\n"
                "0. Back"
            )

    # 2) Find transport (placeholder)
    if choice == "2":
        return _resp(
            "Find transport (soon)\n"
            "1. Boda / Rider\n"
            "2. Tuktuk\n"
            "3. Bus\n"
            "0. Back"
        )

    # 3) My trips (placeholder)
    if choice == "3":
        return _resp("My trips (soon)\n0. Back")

    return _resp("Invalid option.\n0. Back")




# ============================================================
# Businesses (robust v2) - avoids 500s, uses providers table if present
# ============================================================


# ============================================================
# Change place V3 (safe) — persists user_prefs.village
# ============================================================
def handle_change_place_v3(parts, phone: str):
    # parts[0] == "4"
    if parts == ["4"]:
        return ussd_response(
            "CON Choose your area:\n"
            "1. Village\n"
            "2. Town/City\n"
            "3. Airport\n"
            "0. Back"
        ), 200

    if len(parts) >= 2 and parts[1] == "1":
        # Village flow
        if len(parts) == 2:
            return ussd_response(
                "CON Choose your village:\n"
                "1. Bumala\n"
                "2. Butula\n"
                "3. Busia\n"
                "0. Back"
            ), 200

        # Pick village
        choice = parts[2]
        if choice == "0":
            return ussd_response(main_menu()), 200

        # Map choice -> name
        v = None
        try:
            v = village_name_from_choice(choice)
        except Exception:
            pass
        if not v:
            # fallback hard-map
            v = {"1": "Bumala", "2": "Butula", "3": "Busia"}.get(choice)

        if not v:
            return ussd_response("CON Invalid option.\n0. Back"), 200

        # Persist
        try:
            conn = db()
            ensure_user_prefs(conn)
            cur = conn.cursor()
            # Upsert (SQLite)
            cur.execute("""
                INSERT INTO user_prefs (phone, village, updated_at)
                VALUES (?, ?, datetime('now'))
                ON CONFLICT(phone) DO UPDATE SET
                    village=excluded.village,
                    updated_at=datetime('now')
            """, (normalize_phone(phone), v))
            conn.commit()
        except Exception:
            # never break flow
            pass

        return ussd_response(f"CON Location set ✓\nVillage: {v}\n0. Back"), 200

    if len(parts) >= 2 and parts[1] == "2":
        return ussd_response("CON Town/City (soon)\n0. Back"), 200

    if len(parts) >= 2 and parts[1] == "3":
        return ussd_response("CON Airport (soon)\n0. Back"), 200

    if len(parts) >= 2 and parts[1] == "0":
        return ussd_response(main_menu()), 200

    return ussd_response("CON Invalid option.\n0. Back"), 200
def handle_businesses_v2(parts, session_id: str, phone: str):
    """
    Businesses flow (safe, never 500):
      2                  -> choose village
      2*<vchoice>         -> list in village
      2*<vchoice>*<idx>   -> detail
    vchoice can be '1/2/3' or a village name.
    """
    try:
        if not parts or parts[0] != "2":
            return "CON Invalid option.\n0. Back"

        # 2 -> village menu
        if len(parts) == 1:
            lines = ["CON Businesses in which village?"]
            for code, name in _biz_village_pairs():
                # ensure codes are 1..N as USSD expects
                # if code isn't numeric, still display sequentially
                lines.append(f"{code}. {name}")
            lines.append("0. Back")
            return "\n".join(lines)

        # back
        if parts[1] == "0":
            return "CON " + main_menu(phone)

        v = _biz_village_from_choice(parts[1])
        if not v:
            return "CON Invalid village.\n0. Back"

        conn = db()
        cur = conn.cursor()
        cur.execute("""
            SELECT phone, name, COALESCE(current_landmark,'') AS landmark
            FROM providers
            WHERE lower(trim(provider_type))='business'
              AND trim(village)=trim(?)
            ORDER BY name
            LIMIT 20
        """, (v,))
        rows = cur.fetchall() or []

        # 2*<v> -> list
        if len(parts) == 2:
            lines = [f"CON Businesses in {v}"]
            if not rows:
                lines.append("No businesses yet.")
                lines.append("0. Back")
                return "\n".join(lines)
            for i, r in enumerate(rows, start=1):
                nm = (r["name"] if hasattr(r, "__getitem__") else r[1]) or "Business"
                lines.append(f"{i}. {nm} ->")
            lines.append("0. Back")
            return "\n".join(lines)

        # 2*<v>*<idx>
        idx_raw = (parts[2] or "").strip() if len(parts) >= 3 else ""
        if idx_raw == "0":
            return f"CON Businesses in {v}\n0. Back"

        try:
            idx = int(idx_raw) - 1
        except Exception:
            return "CON Invalid option.\n0. Back"

        if idx < 0 or idx >= len(rows):
            return "CON Invalid business.\n0. Back"

        r = rows[idx]
        bphone = r["phone"] if hasattr(r, "__getitem__") else r[0]
        bname  = r["name"] if hasattr(r, "__getitem__") else r[1]
        blm    = r["landmark"] if hasattr(r, "__getitem__") else r[2]

        lines = ["CON Business", f"Name: {bname}", f"Phone: {bphone}"]
        if blm:
            lines.append(f"Place: {blm}")
        lines.append("0. Back")
        return "\n".join(lines)

    except Exception:
        return "CON Businesses\nTemporary error.\n0. Back"

