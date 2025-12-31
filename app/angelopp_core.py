from __future__ import annotations

import os
import re
import sqlite3
import requests
from typing import List, Tuple, Optional, Dict

# =========================
# Angelopp USSD v1 (Bumala)
# - Uses same bumala.db
# - New organization: role first (customer/provider)
# - Services + provider services
# - Landmarks + nearest + fairness
# - Phone numbers hidden
# =========================

MAX_LIST = 10
ICON_GO = "->"
ICON_STAR = "*"
ICON_CHECK = "OK"

DB_PATH = os.path.join(os.path.dirname(__file__), "bumala.db")

# -------------------------
# Optional relative_distance integration
# -------------------------
try:
    from relative_distance import PersonLocation, rank_drivers  # type: ignore
    HAS_RELATIVE_DISTANCE = True
except Exception:
    HAS_RELATIVE_DISTANCE = False
    PersonLocation = None
    rank_drivers = None

# -------------------------
# Basic helpers
# -------------------------
def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def ussd_response(msg: str) -> str:
    return msg

def digits_only(s: str) -> str:
    return re.sub(r"\D+", "", s or "")

def normalize_phone(phone: str) -> str:
    p = (phone or "").strip()
    if p.startswith("+"):
        return "+" + digits_only(p)
    d = digits_only(p)
    if d.startswith("254"):
        return "+" + d
    if d.startswith("0") and len(d) >= 10:
        return "+254" + d[1:]
    return "+" + d

def mask_phone(phone: str) -> str:
    p = normalize_phone(phone)
    d = digits_only(p)
    if len(d) < 6:
        return p
    return f"+{d[:3]}***{d[-3:]}"

def parse_text(text: str) -> List[str]:
    if not text:
        return []
    return text.split("*")

def _clean_text(s: str, max_len: int) -> str:
    s = (s or "").strip()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"[^0-9A-Za-z \-,'/().]", "", s)
    return s[:max_len].strip()

def pick_from_list(title: str, items: List[Tuple[str, str]]) -> str:
    lines = [f"CON {title}"]
    for k, v in items[:MAX_LIST]:
        lines.append(f"{k}. {v}")
    lines.append("0. Back")
    return "\n".join(lines)


# -------------------------
# Outixs integration (minimal)
# -------------------------
OUTIXS_URL = os.environ.get("OUTIXS_URL", "http://127.0.0.1:8080")

def outixs_ride_completed(internal_id: str, rider_phone: str | None = None) -> None:
    """
    Minimal anchor: only store that a job was completed.
    Angelopp must never fail if Outixs is down.
    """
    try:
        payload = {
            "recognized": True,
            "non_trivial": True,
            "transition_type": "RIDE_COMPLETED",
            "transition": {
                "kind": "ride_completed",
                "internal_id": str(internal_id),
                "rider_phone": str(rider_phone) if rider_phone else None
            },
            "context": {
                "source": "angelopp",
                "channel": "ussd"
            }
        }
        requests.post(f"{OUTIXS_URL}/transition", json=payload, timeout=2)
    except Exception as e:
        # keep Angelopp running no matter what
        print("Outixs event failed:", e)

# -------------------------
# Seed menus
# -------------------------
VILLAGES = [("1", "Bumala"), ("2", "Busia"), ("3", "Other")]

DEFAULT_SERVICES = [
    ("Rider (Boda/Tuktuk)", "rider"),
    ("Food / Restaurants", "business"),
    ("Shop / Duka", "business"),
    ("Plumber", "business"),
    ("Carpenter", "business"),
    ("Electrician", "business"),
]

# =========================
# Schema (keeps old tables)
# =========================
def ensure_schema_legacy_minimal() -> None:
    """Keep compatibility if old riders/businesses tables exist. Create if missing."""
    conn = db()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS riders (
        phone TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        village TEXT NOT NULL DEFAULT 'Bumala',
        rider_type TEXT NOT NULL DEFAULT 'Rider',
        sacco TEXT DEFAULT '',
        location TEXT DEFAULT '',
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now'))
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS businesses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        owner_phone TEXT NOT NULL,
        name TEXT NOT NULL,
        category TEXT NOT NULL,
        village TEXT NOT NULL DEFAULT 'Bumala',
        location TEXT DEFAULT '',
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now'))
    )
    """)

    conn.commit()
    conn.close()

def ensure_schema_v2() -> None:
    ensure_schema_legacy_minimal()

    conn = db()
    cur = conn.cursor()

    # Roles: 'customer' or 'provider'
    cur.execute("""
    CREATE TABLE IF NOT EXISTS user_roles (
        phone TEXT PRIMARY KEY,
        role TEXT NOT NULL,
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """)

    # Provider profile (unified)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS providers (
        phone TEXT PRIMARY KEY,
        provider_type TEXT NOT NULL, -- 'rider' or 'business'
        name TEXT NOT NULL,
        village TEXT NOT NULL DEFAULT 'Bumala',
        sacco TEXT DEFAULT '',
        current_landmark TEXT DEFAULT '',
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """)

    # Landmarks (community map)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS landmarks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        village TEXT NOT NULL DEFAULT 'Bumala',
        name TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT '',
        added_by TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_landmarks_village ON landmarks(village)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_landmarks_added_by ON landmarks(added_by)")

    # Service catalog
    cur.execute("""
    CREATE TABLE IF NOT EXISTS services (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        kind TEXT NOT NULL DEFAULT 'any' -- 'rider','business','any'
    )
    """)

    # Provider services
    cur.execute("""
    CREATE TABLE IF NOT EXISTS provider_services (
        phone TEXT NOT NULL,
        service_id INTEGER NOT NULL,
        active INTEGER NOT NULL DEFAULT 1,
        PRIMARY KEY (phone, service_id),
        FOREIGN KEY (phone) REFERENCES providers(phone),
        FOREIGN KEY (service_id) REFERENCES services(id)
    )
    """)

    # Requests created by customers
    cur.execute("""
    CREATE TABLE IF NOT EXISTS service_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_phone TEXT NOT NULL,
        service_id INTEGER NOT NULL,
        village TEXT NOT NULL DEFAULT 'Bumala',
        landmark TEXT NOT NULL DEFAULT '',
        note TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'NEW', -- NEW/OFFERED/ACCEPTED/CLOSED
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """)

    # Offers sent to providers
    cur.execute("""
    CREATE TABLE IF NOT EXISTS request_offers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        request_id INTEGER NOT NULL,
        provider_phone TEXT NOT NULL,
        score REAL NOT NULL DEFAULT 0,
        eta_minutes INTEGER NOT NULL DEFAULT 999,
        status TEXT NOT NULL DEFAULT 'OFFERED', -- OFFERED/ACCEPTED/PASSED
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE(request_id, provider_phone)
    )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_offers_provider ON request_offers(provider_phone, status)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_offers_request ON request_offers(request_id, status)")

    # Assignments (for fairness)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS assignments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        request_id INTEGER NOT NULL UNIQUE,
        provider_phone TEXT NOT NULL,
        assigned_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_assignments_provider_time ON assignments(provider_phone, assigned_at)")

    conn.commit()

    # Seed services if empty
    cur.execute("SELECT COUNT(*) AS c FROM services")
    c = int(cur.fetchone()["c"])
    if c == 0:
        for name, kind in DEFAULT_SERVICES:
            cur.execute("INSERT OR IGNORE INTO services(name, kind) VALUES (?,?)", (name, kind))
        conn.commit()

    conn.close()

# =========================
# Role functions
# =========================
def get_role(phone: str) -> Optional[str]:
    phone = normalize_phone(phone)
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT role FROM user_roles WHERE phone=?", (phone,))
    row = cur.fetchone()
    conn.close()
    return (row["role"] if row else None)

def set_role(phone: str, role: str) -> None:
    phone = normalize_phone(phone)
    conn = db()
    cur = conn.cursor()
    cur.execute("""
    INSERT INTO user_roles(phone, role, updated_at)
    VALUES (?, ?, datetime('now'))
    ON CONFLICT(phone) DO UPDATE SET role=excluded.role, updated_at=datetime('now')
    """, (phone, role))
    conn.commit()
    conn.close()

# =========================
# Providers
# =========================
def upsert_provider(phone: str, provider_type: str, name: str, village: str, sacco: str = "") -> None:
    phone = normalize_phone(phone)
    conn = db()
    cur = conn.cursor()
    cur.execute("""
    INSERT INTO providers(phone, provider_type, name, village, sacco, updated_at)
    VALUES (?, ?, ?, ?, ?, datetime('now'))
    ON CONFLICT(phone) DO UPDATE SET
        provider_type=excluded.provider_type,
        name=excluded.name,
        village=excluded.village,
        sacco=excluded.sacco,
        updated_at=datetime('now')
    """, (phone, provider_type, name, village, sacco))
    conn.commit()
    conn.close()

def get_provider(phone: str) -> Optional[sqlite3.Row]:
    phone = normalize_phone(phone)
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM providers WHERE phone=?", (phone,))
    row = cur.fetchone()
    conn.close()
    return row

def set_provider_landmark(phone: str, landmark: str) -> None:
    phone = normalize_phone(phone)
    conn = db()
    cur = conn.cursor()
    cur.execute("""
    UPDATE providers
    SET current_landmark=?, updated_at=datetime('now')
    WHERE phone=?
    """, (landmark.strip(), phone))
    conn.commit()
    conn.close()

# =========================
# Landmarks
# =========================
def add_landmark(village: str, name: str, description: str, added_by: str) -> None:
    village = (village or "Bumala").strip() or "Bumala"
    name = _clean_text(name, 28)
    description = _clean_text(description, 60)
    added_by = normalize_phone(added_by)

    conn = db()
    cur = conn.cursor()
    cur.execute("""
    INSERT INTO landmarks(village, name, description, added_by)
    VALUES (?, ?, ?, ?)
    """, (village, name, description, added_by))
    conn.commit()
    conn.close()

def list_landmarks(village: str, limit: int = 8) -> List[sqlite3.Row]:
    conn = db()
    cur = conn.cursor()
    cur.execute("""
    SELECT id, name, description
    FROM landmarks
    WHERE village=?
    ORDER BY created_at DESC
    LIMIT ?
    """, (village, limit))
    rows = cur.fetchall()
    conn.close()
    return rows

# =========================
# Services
# =========================
def list_services(kind: Optional[str] = None) -> List[sqlite3.Row]:
    conn = db()
    cur = conn.cursor()
    if kind in ("rider", "business"):
        cur.execute("SELECT id, name, kind FROM services WHERE kind=? OR kind='any' ORDER BY id ASC", (kind,))
    else:
        cur.execute("SELECT id, name, kind FROM services ORDER BY id ASC")
    rows = cur.fetchall()
    conn.close()
    return rows

def provider_set_service(phone: str, service_id: int, active: int) -> None:
    phone = normalize_phone(phone)
    conn = db()
    cur = conn.cursor()
    cur.execute("""
    INSERT INTO provider_services(phone, service_id, active)
    VALUES (?, ?, ?)
    ON CONFLICT(phone, service_id) DO UPDATE SET active=excluded.active
    """, (phone, int(service_id), int(active)))
    conn.commit()
    conn.close()

def provider_services(phone: str) -> List[int]:
    phone = normalize_phone(phone)
    conn = db()
    cur = conn.cursor()
    cur.execute("""
    SELECT service_id FROM provider_services
    WHERE phone=? AND active=1
    """, (phone,))
    ids = [int(r["service_id"]) for r in cur.fetchall()]
    conn.close()
    return ids

# =========================
# Fairness + offers
# =========================
def provider_recent_assignments(phone: str, hours: int = 24) -> int:
    phone = normalize_phone(phone)
    conn = db()
    cur = conn.cursor()
    cur.execute(f"""
    SELECT COUNT(*) AS c
    FROM assignments
    WHERE provider_phone=?
      AND datetime(assigned_at) >= datetime('now', '-{int(hours)} hours')
    """, (phone,))
    c = int(cur.fetchone()["c"])
    conn.close()
    return c

def compute_penalty_minutes(phone: str) -> int:
    # Simple fairness: +2 minutes per assignment in last 24 hours
    c = provider_recent_assignments(phone, hours=24)
    return 2 * c

def estimate_eta_minutes(customer_landmark: str, provider_landmark: str) -> int:
    # If relative_distance exists, we rely on ranking/eta in the PersonLocation.
    # Otherwise: cheap heuristic.
    cl = (customer_landmark or "").strip().lower()
    pl = (provider_landmark or "").strip().lower()
    if not cl or not pl:
        return 12
    if cl == pl:
        return 2
    # same first word heuristic
    if cl.split(" ")[0] == pl.split(" ")[0]:
        return 5
    return 9

def get_candidate_providers(service_id: int, village: str, kind_hint: Optional[str]) -> List[sqlite3.Row]:
    conn = db()
    cur = conn.cursor()

    # Providers who offer this service AND are in village
    cur.execute("""
    SELECT p.phone, p.provider_type, p.name, p.village, p.sacco, p.current_landmark
    FROM providers p
    JOIN provider_services ps ON ps.phone = p.phone
    WHERE ps.service_id=? AND ps.active=1
      AND p.village=?
    ORDER BY p.updated_at DESC
    """, (int(service_id), village))
    rows = cur.fetchall()
    conn.close()
    return rows

def create_request(customer_phone: str, service_id: int, village: str, landmark: str, note: str) -> int:
    customer_phone = normalize_phone(customer_phone)
    village = (village or "Bumala").strip() or "Bumala"
    landmark = _clean_text(landmark, 28)
    note = _clean_text(note, 40)

    conn = db()
    cur = conn.cursor()
    cur.execute("""
    INSERT INTO service_requests(customer_phone, service_id, village, landmark, note, status)
    VALUES (?, ?, ?, ?, ?, 'NEW')
    """, (customer_phone, int(service_id), village, landmark, note))
    rid = int(cur.lastrowid)
    conn.commit()
    conn.close()
    return rid

def build_offers(request_id: int, max_offers: int = 5) -> int:
    conn = db()
    cur = conn.cursor()
    cur.execute("""
    SELECT id, customer_phone, service_id, village, landmark
    FROM service_requests
    WHERE id=?
    """, (int(request_id),))
    req = cur.fetchone()
    if not req:
        conn.close()
        return 0

    service_id = int(req["service_id"])
    village = req["village"]
    customer_landmark = req["landmark"] or ""

    # Determine service kind for filtering services menu only; providers already filtered by provider_services.
    cur.execute("SELECT kind FROM services WHERE id=?", (service_id,))
    sk = cur.fetchone()
    kind_hint = (sk["kind"] if sk else None)

    conn.close()

    candidates = get_candidate_providers(service_id, village, kind_hint)

    scored = []
    for p in candidates:
        p_phone = p["phone"]
        p_lm = (p["current_landmark"] or "").strip()
        eta = estimate_eta_minutes(customer_landmark, p_lm)
        penalty = compute_penalty_minutes(p_phone)
        eff_eta = eta + penalty
        score = float(eff_eta)  # lower is better
        scored.append((score, eta, penalty, p_phone))

    scored.sort(key=lambda x: x[0])
    top = scored[:max_offers]

    if not top:
        return 0

    conn = db()
    cur = conn.cursor()
    inserted = 0
    for score, eta, penalty, p_phone in top:
        try:
            cur.execute("""
            INSERT OR IGNORE INTO request_offers(request_id, provider_phone, score, eta_minutes, status)
            VALUES (?, ?, ?, ?, 'OFFERED')
            """, (int(request_id), normalize_phone(p_phone), float(score), int(eta + penalty)))
            if cur.rowcount > 0:
                inserted += 1
        except Exception:
            pass

    # Mark request as OFFERED
    cur.execute("UPDATE service_requests SET status='OFFERED' WHERE id=?", (int(request_id),))
    conn.commit()
    conn.close()
    return inserted

def provider_pending_offers(phone: str, limit: int = 5) -> List[sqlite3.Row]:
    phone = normalize_phone(phone)
    conn = db()
    cur = conn.cursor()
    cur.execute("""
    SELECT ro.id AS offer_id, ro.request_id, ro.eta_minutes, sr.village, sr.landmark, sr.note
    FROM request_offers ro
    JOIN service_requests sr ON sr.id = ro.request_id
    WHERE ro.provider_phone=? AND ro.status='OFFERED'
    ORDER BY ro.created_at DESC
    LIMIT ?
    """, (phone, limit))
    rows = cur.fetchall()
    conn.close()
    return rows

def accept_offer(provider_phone: str, offer_id: int) -> bool:
    provider_phone = normalize_phone(provider_phone)
    conn = db()
    cur = conn.cursor()

    # Fetch offer
    cur.execute("""
    SELECT request_id FROM request_offers
    WHERE id=? AND provider_phone=? AND status='OFFERED'
    """, (int(offer_id), provider_phone))
    row = cur.fetchone()
    if not row:
        conn.close()
        return False
    request_id = int(row["request_id"])

    # Ensure not already assigned
    cur.execute("SELECT 1 FROM assignments WHERE request_id=?", (request_id,))
    if cur.fetchone():
        # Mark offer as passed
        cur.execute("UPDATE request_offers SET status='PASSED' WHERE id=?", (int(offer_id),))
        conn.commit()
        conn.close()
        return False

    # Assign
    cur.execute("INSERT INTO assignments(request_id, provider_phone) VALUES (?, ?)", (request_id, provider_phone))
    cur.execute("UPDATE request_offers SET status='ACCEPTED' WHERE id=?", (int(offer_id),))
    cur.execute("UPDATE service_requests SET status='ACCEPTED' WHERE id=?", (request_id,))

    # Other offers for this request -> PASSED
    cur.execute("""
    UPDATE request_offers
    SET status='PASSED'
    WHERE request_id=? AND id<>?
    """, (request_id, int(offer_id)))

    conn.commit()
    conn.close()
    return True

def pass_offer(provider_phone: str, offer_id: int) -> bool:
    provider_phone = normalize_phone(provider_phone)
    conn = db()
    cur = conn.cursor()
    cur.execute("""
    UPDATE request_offers
    SET status='PASSED'
    WHERE id=? AND provider_phone=? AND status='OFFERED'
    """, (int(offer_id), provider_phone))
    ok = (cur.rowcount > 0)
    conn.commit()
    conn.close()
    return ok


# =========================
# Completing jobs (minimal)
# =========================
def provider_active_jobs(phone: str, limit: int = 8) -> List[sqlite3.Row]:
    phone = normalize_phone(phone)
    conn = db()
    cur = conn.cursor()
    cur.execute("""
    SELECT sr.id AS request_id, s.name AS service_name, sr.landmark, sr.note, sr.status
    FROM assignments a
    JOIN service_requests sr ON sr.id = a.request_id
    JOIN services s ON s.id = sr.service_id
    WHERE a.provider_phone=?
      AND sr.status='ACCEPTED'
    ORDER BY sr.created_at DESC
    LIMIT ?
    """, (phone, int(limit)))
    rows = cur.fetchall()
    conn.close()
    return rows

def complete_job(provider_phone: str, request_id: int) -> bool:
    """
    Mark job as CLOSED (completed) ONLY if it belongs to this provider and is ACCEPTED.
    Then anchor to Outixs.
    """
    provider_phone = normalize_phone(provider_phone)
    conn = db()
    cur = conn.cursor()

    cur.execute("""
    SELECT 1
    FROM assignments a
    JOIN service_requests sr ON sr.id = a.request_id
    WHERE a.provider_phone=? AND a.request_id=? AND sr.status='ACCEPTED'
    """, (provider_phone, int(request_id)))
    if not cur.fetchone():
        conn.close()
        return False

    cur.execute("UPDATE service_requests SET status='CLOSED' WHERE id=?", (int(request_id),))
    conn.commit()
    conn.close()

    # Anchor completion (only after DB commit)
    outixs_ride_completed(f"angelopp_req_{int(request_id)}", provider_phone)
    return True

# =========================
# UI Menus
# =========================
def root_menu(phone: str) -> str:
    role = get_role(phone)
    if role == "customer":
        return customer_menu()
    if role == "provider":
        return provider_menu()
    return "\n".join([
        "CON Angelopp Bumala",
        "1. I am a Customer",
        "2. I am a Service Provider",
        "0. Exit"
    ])

def customer_menu() -> str:
    return "\n".join([
        "CON Customer",
        f"1. Find a service {ICON_GO}",
        "2. My requests",
        "3. Set my landmark",
        "9. Switch role",
        "0. Exit"
    ])

def provider_menu() -> str:
    return "\n".join([
        "CON Service Provider",
        "1. My profile (register/update)",
        "2. My services (add/remove)",
        "3. Update my landmark",
        f"4. Incoming requests {ICON_GO}",
        "5. Complete a job",
        "9. Switch role",
        "0. Exit"
    ])
def village_menu(title: str = "Choose village:") -> str:
    return pick_from_list(title, VILLAGES)

def village_key_to_name(k: str) -> str:
    for kk, name in VILLAGES:
        if kk == k:
            return name
    return "Bumala"

# =========================
# Customer flows
# =========================
def handle_customer(parts: List[str], session_id: str, phone: str) -> Tuple[str, int]:
    # parts[0] == "C" internal only, we route by root numbers below
    # customer menu items:
    # 1 find service, 2 my requests, 3 set landmark

    if len(parts) == 1:
        return ussd_response(customer_menu()), 200

    choice = parts[1].strip()

    if choice == "0":
        return "END Bye.", 200

    if choice == "9":
        set_role(phone, "provider")
        return ussd_response(provider_menu()), 200

    if choice == "1":
        return handle_customer_find_service(parts, phone)

    if choice == "2":
        return handle_customer_my_requests(parts, phone)

    if choice == "3":
        return handle_customer_set_landmark(parts, phone)

    return ussd_response(customer_menu() + "\n\nInvalid."), 200

def handle_customer_set_landmark(parts: List[str], phone: str) -> Tuple[str, int]:
    # Customer landmark stored as a "provider" row? no.
    # We'll store it in user_roles via an extra table to keep it simple:
    # We'll reuse providers table for everyone? Better: small table customer_prefs.
    ensure_customer_prefs_schema()

    if len(parts) == 2:
        return ussd_response(
            "CON Set your landmark\n"
            "Type a landmark name (e.g. Market Gate)\n"
            "0. Back"
        ), 200
    if len(parts) == 3:
        if parts[2] == "0":
            return ussd_response(customer_menu()), 200
        lm = _clean_text(parts[2], 28)
        if len(lm) < 3:
            return ussd_response("CON Too short.\n0. Back"), 200
        set_customer_landmark(phone, lm)
        return ("END Saved ✓\nLandmark set.", 200)

    return ussd_response("CON Invalid.\n0. Back"), 200

def ensure_customer_prefs_schema():
    conn = db()
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS customer_prefs (
        phone TEXT PRIMARY KEY,
        village TEXT NOT NULL DEFAULT 'Bumala',
        landmark TEXT NOT NULL DEFAULT '',
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """)
    conn.commit()
    conn.close()

def set_customer_landmark(phone: str, landmark: str) -> None:
    phone = normalize_phone(phone)
    conn = db()
    cur = conn.cursor()
    cur.execute("""
    INSERT INTO customer_prefs(phone, landmark, updated_at)
    VALUES (?, ?, datetime('now'))
    ON CONFLICT(phone) DO UPDATE SET
        landmark=excluded.landmark,
        updated_at=datetime('now')
    """, (phone, landmark.strip()))
    conn.commit()
    conn.close()

def get_customer_landmark(phone: str) -> str:
    phone = normalize_phone(phone)
    ensure_customer_prefs_schema()
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT landmark FROM customer_prefs WHERE phone=?", (phone,))
    row = cur.fetchone()
    conn.close()
    return (row["landmark"] if row and row["landmark"] else "")

def handle_customer_my_requests(parts: List[str], phone: str) -> Tuple[str, int]:
    phone = normalize_phone(phone)
    conn = db()
    cur = conn.cursor()
    cur.execute("""
    SELECT sr.id, sr.status, s.name AS service_name, sr.village, sr.landmark
    FROM service_requests sr
    JOIN services s ON s.id = sr.service_id
    WHERE sr.customer_phone=?
    ORDER BY sr.created_at DESC
    LIMIT 8
    """, (phone,))
    rows = cur.fetchall()
    conn.close()

    lines = ["CON My requests"]
    if not rows:
        lines += ["No requests yet.", "0. Back"]
        return ussd_response("\n".join(lines)), 200

    for r in rows:
        lines.append(f"{r['id']}. {r['service_name']} [{r['status']}] @ {r['landmark']}")
    lines.append("0. Back")
    return ussd_response("\n".join(lines)), 200

def handle_customer_find_service(parts: List[str], phone: str) -> Tuple[str, int]:
    # Flow:
    # C*1 -> choose service
    # C*1*<serviceIndex> -> choose village
    # C*1*<serviceIndex>*<villageKey> -> choose landmark (existing or type new)
    # C*1*<serviceIndex>*<villageKey>*<lmChoice> -> note or submit
    phone = normalize_phone(phone)

    # Step 1: list services (all)
    if len(parts) == 2:
        services = list_services()
        items = [(str(i+1), s["name"]) for i, s in enumerate(services[:MAX_LIST])]
        return ussd_response(pick_from_list("Choose service:", items)), 200

    # Step 2: parse service selection
    services = list_services()
    try:
        sidx = int(parts[2])
    except Exception:
        return ussd_response("CON Invalid.\n0. Back"), 200
    if sidx == 0:
        return ussd_response(customer_menu()), 200
    if sidx < 1 or sidx > min(len(services), MAX_LIST):
        return ussd_response("CON Invalid service.\n0. Back"), 200
    service_id = int(services[sidx-1]["id"])

    # Step 3: choose village
    if len(parts) == 3:
        return ussd_response(village_menu("Service in which village?")), 200

    if parts[3] == "0":
        return ussd_response("CON Choose service:\n0. Back"), 200

    village = village_key_to_name(parts[3])

    # Step 4: choose landmark: show last landmarks + option to type new
    if len(parts) == 4:
        lms = list_landmarks(village, limit=6)
        lines = [f"CON Choose landmark ({village})"]
        if lms:
            for i, lm in enumerate(lms, 1):
                lines.append(f"{i}. {lm['name']}")
            lines.append("7. Type new landmark")
        else:
            lines.append("7. Type new landmark")
        lines.append("0. Back")
        return ussd_response("\n".join(lines)), 200

    if parts[4] == "0":
        return ussd_response(village_menu("Service in which village?")), 200

    # Step 5: landmark selection or typing
    landmark = ""
    if parts[4] == "7":
        if len(parts) == 5:
            return ussd_response("CON Type landmark name:\n0. Back"), 200
        if parts[5] == "0":
            return ussd_response(customer_menu()), 200
        landmark = _clean_text(parts[5], 28)
        if len(landmark) < 3:
            return ussd_response("CON Too short.\n0. Back"), 200
    else:
        # pick from list
        lms = list_landmarks(village, limit=6)
        try:
            lm_idx = int(parts[4])
        except Exception:
            return ussd_response("CON Invalid.\n0. Back"), 200
        if lm_idx < 1 or lm_idx > len(lms):
            return ussd_response("CON Invalid landmark.\n0. Back"), 200
        landmark = lms[lm_idx-1]["name"]

    # Step 6: optional note
    # If user typed new landmark, note is parts[6] else note is parts[5]
    note_part_index = 6 if parts[4] == "7" else 5
    if len(parts) <= note_part_index:
        return ussd_response(
            "CON Add a short note (optional)\n"
            "Or type 0 to skip.\n"
            "Example: near school gate"
        ), 200

    note = parts[note_part_index]
    if note == "0":
        note = ""

    # Create request + offers
    req_id = create_request(phone, service_id, village, landmark, note)
    offer_count = build_offers(req_id, max_offers=5)

    if offer_count == 0:
        return (
            "END Request saved ✓\n"
            "No providers available yet.\n"
            "Try again later or add providers.",
            200
        )

    return (
        "END Request saved ✓\n"
        f"Request #{req_id}\n"
        "Phone numbers stay hidden.\n"
        "SACCO/admin can connect you.",
        200
    )

# =========================
# Provider flows
# =========================
def handle_provider(parts: List[str], session_id: str, phone: str) -> Tuple[str, int]:
    if len(parts) == 1:
        return ussd_response(provider_menu()), 200

    choice = parts[1].strip()

    if choice == "0":
        return "END Bye.", 200

    if choice == "9":
        set_role(phone, "customer")
        return ussd_response(customer_menu()), 200

    if choice == "1":
        return handle_provider_profile(parts, phone)

    if choice == "2":
        return handle_provider_services(parts, phone)

    if choice == "3":
        return handle_provider_landmark(parts, phone)

    if choice == "4":
        return handle_provider_incoming(parts, phone)


    if choice == "5":
        return handle_provider_complete(parts, phone)

    return ussd_response(provider_menu() + "\n\nInvalid."), 200

def handle_provider_profile(parts: List[str], phone: str) -> Tuple[str, int]:
    # Flow:
    # P*1 -> choose type rider/business
    # P*1*1 -> name
    # P*1*1*<name> -> village
    # P*1*1*<name>*<villageKey> -> sacco (optional)
    phone = normalize_phone(phone)

    if len(parts) == 2:
        return ussd_response("CON Profile\n1. Rider\n2. Business owner\n0. Back"), 200

    if parts[2] == "0":
        return ussd_response(provider_menu()), 200

    if parts[2] not in ("1", "2"):
        return ussd_response("CON Invalid.\n0. Back"), 200

    ptype = "rider" if parts[2] == "1" else "business"

    if len(parts) == 3:
        return ussd_response("CON Your name?"), 200

    name = _clean_text(parts[3], 20)
    if len(name) < 2:
        return ussd_response("CON Name too short.\n0. Back"), 200

    if len(parts) == 4:
        return ussd_response(village_menu("Your village?")), 200

    if parts[4] == "0":
        return ussd_response(provider_menu()), 200

    village = village_key_to_name(parts[4])

    if len(parts) == 5:
        return ussd_response("CON SACCO name? (or 0 to skip)"), 200

    sacco = _clean_text(parts[5], 20)
    if sacco == "0":
        sacco = ""

    upsert_provider(phone, ptype, name, village, sacco)

    # Helpful: if rider, also mirror into legacy riders table (optional but nice)
    if ptype == "rider":
        mirror_into_legacy_riders(phone, name, village, sacco)

    return (
        "END Saved ✓\n"
        f"{name} ({ptype})\n"
        f"{village}",
        200
    )

def mirror_into_legacy_riders(phone: str, name: str, village: str, sacco: str) -> None:
    conn = db()
    cur = conn.cursor()
    cur.execute("""
    INSERT INTO riders(phone, name, village, rider_type, sacco, location, created_at, updated_at)
    VALUES (?, ?, ?, 'Rider', ?, '', datetime('now'), datetime('now'))
    ON CONFLICT(phone) DO UPDATE SET
        name=excluded.name,
        village=excluded.village,
        sacco=excluded.sacco,
        updated_at=datetime('now')
    """, (normalize_phone(phone), name, village, sacco))
    conn.commit()
    conn.close()

def handle_provider_landmark(parts: List[str], phone: str) -> Tuple[str, int]:
    phone = normalize_phone(phone)
    p = get_provider(phone)
    if not p:
        return ussd_response("CON Register your profile first.\n(Provider Menu -> 1)\n0. Back"), 200

    if len(parts) == 2:
        # show recent landmarks in provider village
        village = p["village"]
        lms = list_landmarks(village, limit=6)
        lines = [f"CON Update landmark ({village})"]
        if lms:
            for i, lm in enumerate(lms, 1):
                lines.append(f"{i}. {lm['name']}")
            lines.append("7. Type new landmark")
        else:
            lines.append("7. Type new landmark")
        lines.append("0. Back")
        return ussd_response("\n".join(lines)), 200

    if parts[2] == "0":
        return ussd_response(provider_menu()), 200

    village = p["village"]
    landmark = ""

    if parts[2] == "7":
        if len(parts) == 3:
            return ussd_response("CON Type landmark name:\n0. Back"), 200
        if parts[3] == "0":
            return ussd_response(provider_menu()), 200
        landmark = _clean_text(parts[3], 28)
        if len(landmark) < 3:
            return ussd_response("CON Too short.\n0. Back"), 200
        # add to community landmarks too (optional)
        add_landmark(village, landmark, "Added by provider", phone)
    else:
        lms = list_landmarks(village, limit=6)
        try:
            idx = int(parts[2])
        except Exception:
            return ussd_response("CON Invalid.\n0. Back"), 200
        if idx < 1 or idx > len(lms):
            return ussd_response("CON Invalid.\n0. Back"), 200
        landmark = lms[idx-1]["name"]

    set_provider_landmark(phone, landmark)

    # also mirror into legacy riders/businesses location if it exists
    conn = db()
    cur = conn.cursor()
    cur.execute("UPDATE riders SET location=?, updated_at=datetime('now') WHERE phone=?", (landmark, phone))
    conn.commit()
    conn.close()

    return ("END Landmark updated ✓", 200)

def handle_provider_services(parts: List[str], phone: str) -> Tuple[str, int]:
    phone = normalize_phone(phone)
    p = get_provider(phone)
    if not p:
        return ussd_response("CON Register your profile first.\n(Provider Menu -> 1)\n0. Back"), 200

    ptype = p["provider_type"]
    services = list_services(kind=ptype)
    my_ids = set(provider_services(phone))

    # P*2 -> show list with +/-
    if len(parts) == 2:
        lines = ["CON My services (toggle)"]
        for i, s in enumerate(services[:MAX_LIST], 1):
            mark = "[+]" if int(s["id"]) in my_ids else "[ ]"
            lines.append(f"{i}. {mark} {s['name']}")
        lines.append("0. Back")
        return ussd_response("\n".join(lines)), 200

    if parts[2] == "0":
        return ussd_response(provider_menu()), 200

    try:
        idx = int(parts[2])
    except Exception:
        return ussd_response("CON Invalid.\n0. Back"), 200
    if idx < 1 or idx > min(len(services), MAX_LIST):
        return ussd_response("CON Invalid.\n0. Back"), 200

    sid = int(services[idx-1]["id"])
    new_active = 0 if sid in my_ids else 1
    provider_set_service(phone, sid, new_active)

    return ussd_response("CON Updated ✓\n0. Back"), 200

def handle_provider_incoming(parts: List[str], phone: str) -> Tuple[str, int]:
    phone = normalize_phone(phone)
    p = get_provider(phone)
    if not p:
        return ussd_response("CON Register your profile first.\n(Provider Menu -> 1)\n0. Back"), 200

    offers = provider_pending_offers(phone, limit=5)

    # P*4 -> list
    if len(parts) == 2:
        lines = ["CON Incoming requests"]
        if not offers:
            lines += ["No offers yet.", "0. Back"]
            return ussd_response("\n".join(lines)), 200
        for i, o in enumerate(offers, 1):
            note = (o["note"] or "").strip()
            note_txt = f" - {note}" if note else ""
            lines.append(f"{i}. Req#{o['request_id']} ~{o['eta_minutes']}m @ {o['landmark']}{note_txt}")
        lines.append("0. Back")
        return ussd_response("\n".join(lines)), 200

    if parts[2] == "0":
        return ussd_response(provider_menu()), 200

    # P*4*<index> -> accept/pass menu
    try:
        idx = int(parts[2])
    except Exception:
        return ussd_response("CON Invalid.\n0. Back"), 200
    if idx < 1 or idx > len(offers):
        return ussd_response("CON Invalid.\n0. Back"), 200

    offer_id = int(offers[idx-1]["offer_id"])

    if len(parts) == 3:
        return ussd_response(
            "CON Choose action\n"
            "1. Accept\n"
            "2. Pass\n"
            "0. Back"
        ), 200

    action = parts[3].strip()
    if action == "0":
        return ussd_response(provider_menu()), 200
    if action == "1":
        ok = accept_offer(phone, offer_id)
        if ok:
            return (
                "END Accepted ✓\n"
                "Phone numbers stay hidden.\n"
                "SACCO/admin can connect you.",
                200
            )
        return ("END Not available.\n(Already assigned)", 200)

    if action == "2":
        pass_offer(phone, offer_id)
        return ("END Passed ✓", 200)

    return ussd_response("CON Invalid.\n0. Back"), 200

def handle_provider_complete(parts: List[str], phone: str) -> Tuple[str, int]:
    phone = normalize_phone(phone)
    p = get_provider(phone)
    if not p:
        return ussd_response("CON Register your profile first.\n(Provider Menu -> 1)\n0. Back"), 200

    jobs = provider_active_jobs(phone, limit=8)

    # P*5 -> list active jobs
    if len(parts) == 2:
        lines = ["CON Complete a job"]
        if not jobs:
            lines += ["No active jobs.", "0. Back"]
            return ussd_response("\n".join(lines)), 200

        for i, j in enumerate(jobs, 1):
            note = (j["note"] or "").strip()
            note_txt = f" - {note}" if note else ""
            lines.append(f"{i}. Req#{j['request_id']} {j['service_name']} @ {j['landmark']}{note_txt}")
        lines.append("0. Back")
        return ussd_response("\n".join(lines)), 200

    if parts[2] == "0":
        return ussd_response(provider_menu()), 200

    # P*5*<index> -> confirm
    try:
        idx = int(parts[2])
    except Exception:
        return ussd_response("CON Invalid.\n0. Back"), 200
    if idx < 1 or idx > len(jobs):
        return ussd_response("CON Invalid.\n0. Back"), 200

    request_id = int(jobs[idx-1]["request_id"])

    if len(parts) == 3:
        return ussd_response(
            f"CON Mark Req#{request_id} as completed?\n"
            "1. Yes, completed\n"
            "0. Back"
        ), 200

    if parts[3].strip() == "0":
        return ussd_response(provider_menu()), 200

    if parts[3].strip() == "1":
        ok = complete_job(phone, request_id)
        if ok:
            return ("END Completed ✓\nSaved to Outixs.", 200)
        return ("END Not possible.\n(Already closed or not yours)", 200)

    return ussd_response("CON Invalid.\n0. Back"), 200

# =========================
# Main router
# =========================
def handle_ussd(session_id: str, phone_number: str, text: str) -> Tuple[str, int]:
    ensure_schema_v2()
    phone = normalize_phone(phone_number)
    parts = parse_text(text)

    # Root: if no role chosen yet, show role menu
    if not parts:
        return ussd_response(root_menu(phone)), 200

    # Handle root-level exit
    if parts == ["0"]:
        return "END Bye.", 200

    # If user not set role yet: interpret first choice as role
    role = get_role(phone)

    if role is None:
        # expecting: 1 customer / 2 provider / 0 exit
        c = parts[0].strip()
        if c == "1":
            set_role(phone, "customer")
            return ussd_response(customer_menu()), 200
        if c == "2":
            set_role(phone, "provider")
            return ussd_response(provider_menu()), 200
        if c == "0":
            return "END Bye.", 200
        return ussd_response(root_menu(phone)), 200

    # Role already chosen: we route by role menus
    # We map the user input to an internal prefix:
    # customer: treat as C*<choice>*...
    # provider: treat as P*<choice>*...
    if role == "customer":
        # Switching role is customer menu 9
        parts2 = ["C"] + parts
        # customer menu expects parts2[1] == choice
        return handle_customer(parts2, session_id, phone)

    if role == "provider":
        parts2 = ["P"] + parts
        return handle_provider(parts2, session_id, phone)

    # Fallback
    return ussd_response(root_menu(phone)), 200

