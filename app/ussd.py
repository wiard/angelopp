from __future__ import annotations
# --- Relative distance engine ---
from relative_distance import PersonLocation, rank_drivers

# /opt/bumala_riders/bumala_riders_ussd.py



# USSD display limits
MAX_LIST = 10

# === LANDMARK HELPERS ===
def save_landmark(phone: str, name: str, description: str):
    import sqlite3
    db = sqlite3.connect("/opt/angelopp/data/bumala.db")
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

# === CHALLENGE_SCHEMA_V1 ===
import re

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
    db = sqlite3.connect("/opt/angelopp/data/bumala.db")
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
DB_PATH = os.path.join(os.path.dirname(__file__), "bumala.db")
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
    cur.execute("CREATE INDEX IF NOT EXISTS idx_landmarks_phone ON landmarks(phone)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_landmarks_added_by ON landmarks(phone)")

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


def main_menu() -> str:
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
    return pick_from_list(title, VILLAGES)


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
    Returns (village, landmark_name) for this phone from most recent landmark entry.
    Falls back to (None, None) if nothing found / not set.
    """
    conn = db()
    try:
        cur = conn.cursor()
        # newest first: prefer created_at then id as tie-breaker
        cur.execute(
            """
            SELECT village, name
            FROM landmarks
            WHERE phone = ?
            ORDER BY datetime(created_at) DESC, id DESC
            LIMIT 1
            """,
            (phone,),
        )
        row = cur.fetchone()
        if not row:
            return (None, None)
        village = row[0]
        landmark = row[1]
        return (village, landmark)
    finally:
        try:
            conn.close()
        except Exception:
            pass


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
    lines = ["CON Nearest riders"]
    if not drivers:
        lines += ["No riders found.", "0. Back"]
        return "\n".join(lines)

    for i, d in enumerate(drivers, 1):
        lm = d.landmark or "Unknown"
        lines.append(f"{i}) {d.phone} ~{d.eta_minutes} min ({lm})")

    lines.append("0. Back")
    return "\n".join(lines)

def handle_ussd(session_id: str, phone_number: str, text: str) -> Tuple[str, int]:
    """
    Africa's Talking POST form fields:
      sessionId, phoneNumber, text
    Must return (body, http_code).
    Body MUST start with CON or END.
    """
    ensure_schema()

    phone = normalize_phone(phone_number)
    parts = parse_text(text)

    # empty -> show main menu
    if not parts:
        return ussd_response(main_menu()), 200

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
        return ussd_response(main_menu()), 200

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

    return ussd_response(main_menu() + "\n\nInvalid option."), 200

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

