import os
import sqlite3
from pathlib import Path

# Prefer /opt/angelopp/data/bumala.db if it exists, else fallback to app/bumala.db
APP_DIR = Path(__file__).resolve().parent
DATA_DB = Path("/opt/angelopp/data/bumala.db")
APP_DB  = APP_DIR / "bumala.db"
DB_PATH = DATA_DB if DATA_DB.exists() else APP_DB

def db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

def ensure_schema():
    with db() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS user_prefs (
            phone TEXT PRIMARY KEY,
            role TEXT,                 -- 'customer' or 'provider'
            area_type TEXT,            -- 'village' | 'town' | 'airport'
            landmark TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        """)
        conn.execute("""
        CREATE TRIGGER IF NOT EXISTS user_prefs_updated
        AFTER UPDATE ON user_prefs
        FOR EACH ROW
        BEGIN
            UPDATE user_prefs SET updated_at = datetime('now') WHERE phone = OLD.phone;
        END;
        """)

def con(msg: str): return "CON " + msg
def end(msg: str): return "END " + msg

def normalize_steps(text: str):
    """
    Africa's Talking style: "1*2*3"
    Interpret:
      - "0"  = back one level
      - "00" = go home (clear)
    """
    if not text:
        return []
    raw = [s for s in text.split("*") if s != ""]
    steps = []
    for s in raw:
        if s == "00":
            steps = []
        elif s == "0":
            if steps:
                steps.pop()
        else:
            steps.append(s)
    return steps

def get_prefs(phone: str):
    with db() as conn:
        row = conn.execute("SELECT * FROM user_prefs WHERE phone=?", (phone,)).fetchone()
        if row:
            return dict(row)
    return {"phone": phone, "role": None, "area_type": None, "landmark": None}

def upsert_prefs(phone: str, role=None, area_type=None, landmark=None):
    current = get_prefs(phone)
    role = role if role is not None else current.get("role")
    area_type = area_type if area_type is not None else current.get("area_type")
    landmark = landmark if landmark is not None else current.get("landmark")

    with db() as conn:
        conn.execute("""
        INSERT INTO user_prefs (phone, role, area_type, landmark)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(phone) DO UPDATE SET
            role=excluded.role,
            area_type=excluded.area_type,
            landmark=excluded.landmark,
            updated_at=datetime('now');
        """, (phone, role, area_type, landmark))

def clear_role(phone: str):
    upsert_prefs(phone, role=None, area_type=None, landmark=None)

def clear_location(phone: str):
    prefs = get_prefs(phone)
    upsert_prefs(phone, role=prefs.get("role"), area_type=None, landmark=None)

def is_onboarded(phone: str):
    p = get_prefs(phone)
    return bool(p.get("role") and p.get("area_type") and p.get("landmark"))

def onboarding_response(session_id: str, phone: str, text: str):
    """
    Returns:
      - a "CON/END ..." string when onboarding still needed
      - None when user is onboarded and main app should handle it
    """
    ensure_schema()

    steps = normalize_steps(text or "")
    prefs = get_prefs(phone)

    # If already onboarded, don't intercept
    if prefs.get("role") and prefs.get("area_type") and prefs.get("landmark"):
        return None

    # ---------- Role ----------
    if not prefs.get("role"):
        if len(steps) >= 1:
            if steps[0] == "1":
                upsert_prefs(phone, role="customer", area_type=None, landmark=None)
                return con("Choose your area:\n1. Village\n2. Town/City\n3. Airport\n0. Back")
            if steps[0] == "2":
                upsert_prefs(phone, role="provider", area_type=None, landmark=None)
                return con("Choose your area:\n1. Village\n2. Town/City\n3. Airport\n0. Back")
            if steps[0] == "0":
                return end("Bye.")
        return con("Angelopp\n1. I am a Customer\n2. I am a Service Provider\n3. Traveler & Airport (back & forth)\n0. Exit")

    # Refresh
    prefs = get_prefs(phone)

    # ---------- Area ----------
    if not prefs.get("area_type"):
        if len(steps) >= 1:
            last = steps[-1]
            if last == "1":
                upsert_prefs(phone, area_type="village", landmark=None)
                return con("Choose landmark (Village):\n"
                           "1. Church\n2. Market\n3. Stage\n4. School\n5. Water point\n9. Type my own\n0. Back")
            if last == "2":
                upsert_prefs(phone, area_type="town", landmark=None)
                return con("Choose landmark (Town):\n"
                           "1. Bus station\n2. Main market\n3. Hospital\n4. Mall/Center\n9. Type my own\n0. Back")
            if last == "3":
                upsert_prefs(phone, area_type="airport", landmark=None)
                return con("Choose landmark (Airport):\n"
                           "1. Arrivals\n2. Departures\n3. Taxi pickup\n4. Parking\n0. Back")
            if last == "0":
                clear_role(phone)
                return con("Angelopp\n1. I am a Customer\n2. I am a Service Provider\n3. Traveler & Airport (back & forth)\n0. Exit")
        return con("Choose your area:\n1. Village\n2. Town/City\n3. Airport\n0. Back")

    # Refresh
    prefs = get_prefs(phone)
    area_type = prefs.get("area_type")

    # ---------- Landmark ----------
    if not prefs.get("landmark"):
        if len(steps) >= 1:
            last = steps[-1]

            if area_type == "village":
                mapping = {"1":"Church","2":"Market","3":"Stage","4":"School","5":"Water point"}
                if last in mapping:
                    upsert_prefs(phone, landmark=mapping[last])
                    return None
                if last == "9":
                    return con("Type your landmark name:\n(Example: Chief camp)\n0. Back")
                # Note: Many USSD gateways are digits-only; free text may not work everywhere.
                # If user enters something else, we keep showing menu.
                return con("Choose landmark (Village):\n"
                           "1. Church\n2. Market\n3. Stage\n4. School\n5. Water point\n9. Type my own\n0. Back")

            if area_type == "town":
                mapping = {"1":"Bus station","2":"Main market","3":"Hospital","4":"Mall/Center"}
                if last in mapping:
                    upsert_prefs(phone, landmark=mapping[last])
                    return None
                if last == "9":
                    return con("Type your landmark name:\n(Example: Shell petrol)\n0. Back")
                return con("Choose landmark (Town):\n"
                           "1. Bus station\n2. Main market\n3. Hospital\n4. Mall/Center\n9. Type my own\n0. Back")

            if area_type == "airport":
                mapping = {"1":"Arrivals","2":"Departures","3":"Taxi pickup","4":"Parking"}
                if last in mapping:
                    upsert_prefs(phone, landmark=mapping[last])
                    return None
                return con("Choose landmark (Airport):\n"
                           "1. Arrivals\n2. Departures\n3. Taxi pickup\n4. Parking\n0. Back")

        # Default show landmark menu
        if area_type == "village":
            return con("Choose landmark (Village):\n"
                       "1. Church\n2. Market\n3. Stage\n4. School\n5. Water point\n9. Type my own\n0. Back")
        if area_type == "town":
            return con("Choose landmark (Town):\n"
                       "1. Bus station\n2. Main market\n3. Hospital\n4. Mall/Center\n9. Type my own\n0. Back")
        if area_type == "airport":
            return con("Choose landmark (Airport):\n"
                       "1. Arrivals\n2. Departures\n3. Taxi pickup\n4. Parking\n0. Back")

    return None
