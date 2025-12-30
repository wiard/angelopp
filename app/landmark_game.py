import sqlite3
from datetime import datetime, timedelta, timezone

DB = "/opt/ussd/market.db"

def _conn():
    return sqlite3.connect(DB)

def ensure_schema():
    conn = _conn()
    cur = conn.cursor()

    # Who added which landmarks
    cur.execute("""
    CREATE TABLE IF NOT EXISTS landmarks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        village TEXT NOT NULL,
        name TEXT NOT NULL,
        created_by_phone TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """)

    # Simple points table (works for customers/riders)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS user_points (
        phone TEXT PRIMARY KEY,
        name TEXT,
        village TEXT,
        role TEXT,
        points INTEGER NOT NULL DEFAULT 0,
        level INTEGER NOT NULL DEFAULT 1,
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """)

    # Prevent unlimited daily claim spam
    cur.execute("""
    CREATE TABLE IF NOT EXISTS challenge_claims (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        phone TEXT NOT NULL,
        challenge_key TEXT NOT NULL,
        claim_date TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE(phone, challenge_key, claim_date)
    )
    """)

    conn.commit()
    conn.close()

def upsert_user(phone: str, name: str, village: str, role: str):
    conn = _conn()
    cur = conn.cursor()
    cur.execute("""
    INSERT INTO user_points(phone, name, village, role, points, level)
    VALUES(?,?,?,?,?,?)
    ON CONFLICT(phone) DO UPDATE SET
        name=excluded.name,
        village=excluded.village,
        role=excluded.role,
        updated_at=datetime('now')
    """, (phone, name, village, role, 0, 1))
    conn.commit()
    conn.close()

def add_points(phone: str, delta: int):
    conn = _conn()
    cur = conn.cursor()
    cur.execute("UPDATE user_points SET points=points+?, updated_at=datetime('now') WHERE phone=?", (delta, phone))
    # If user not in table yet, create a minimal row
    if cur.rowcount == 0:
        cur.execute("INSERT INTO user_points(phone, points, level) VALUES(?,?,?)", (phone, delta, 1))
    # Level rule: every 20 points -> +1 level
    cur.execute("SELECT points FROM user_points WHERE phone=?", (phone,))
    pts = cur.fetchone()[0]
    level = max(1, (pts // 20) + 1)
    cur.execute("UPDATE user_points SET level=? WHERE phone=?", (level, phone))
    conn.commit()
    conn.close()

def get_status(phone: str):
    conn = _conn()
    cur = conn.cursor()
    cur.execute("SELECT name, village, level, points FROM user_points WHERE phone=?", (phone,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    return {"name": row[0], "village": row[1], "level": row[2], "points": row[3]}

def add_landmark(village: str, name: str, phone: str):
    name = (name or "").strip()
    if not name:
        return False, "Empty landmark"
    if len(name) > 32:
        return False, "Too long (max 32 chars)"

    conn = _conn()
    cur = conn.cursor()
    cur.execute("""
    INSERT INTO landmarks(village, name, created_by_phone)
    VALUES(?,?,?)
    """, (village, name, phone))
    conn.commit()
    conn.close()
    return True, "OK"

def claim_daily(phone: str, challenge_key="daily_landmark_claim", points=3):
    today = datetime.now(timezone.utc).date().isoformat()
    conn = _conn()
    cur = conn.cursor()
    try:
        cur.execute("""
        INSERT INTO challenge_claims(phone, challenge_key, claim_date)
        VALUES(?,?,?)
        """, (phone, challenge_key, today))
        conn.commit()
        conn.close()
        add_points(phone, points)
        return True
    except sqlite3.IntegrityError:
        conn.close()
        return False

def _week_range_utc(now=None):
    # Monday 00:00 UTC .. next Monday 00:00 UTC
    now = now or datetime.now(timezone.utc)
    monday = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    next_monday = monday + timedelta(days=7)
    return monday, next_monday

def weekly_landmark_leaderboard(limit=5):
    monday, next_monday = _week_range_utc()
    start = monday.strftime("%Y-%m-%d %H:%M:%S")
    end = next_monday.strftime("%Y-%m-%d %H:%M:%S")

    conn = _conn()
    cur = conn.cursor()

    # For each landmark created this week:
    # - usage: how many rides used that pickup name this week
    # - uniq: distinct customers selecting it this week
    # - done: how many ended DONE
    cur.execute("""
    SELECT
      l.village,
      l.name,
      COUNT(cr.id) AS usage,
      SUM(CASE WHEN cr.status='DONE' THEN 1 ELSE 0 END) AS done,
      COUNT(DISTINCT cr.customer_phone) AS uniq,
      COUNT(DISTINCT l.created_by_phone) AS contributors
    FROM landmarks l
    LEFT JOIN callback_requests cr
      ON cr.pickup = l.name
      AND cr.created_at >= ?
      AND cr.created_at < ?
    WHERE l.created_at >= ?
      AND l.created_at < ?
    GROUP BY l.village, l.name
    """, (start, end, start, end))

    rows = cur.fetchall()
    conn.close()

    scored = []
    for village, name, usage, done, uniq, contributors in rows:
        usage = usage or 0
        done = done or 0
        uniq = uniq or 0
        contributors = contributors or 0
        success_rate = (done / usage) if usage > 0 else 0.0

        # Simple, explainable scoring:
        # - usage is king (real behavior)
        # - success_rate protects from spam landmarks
        # - uniq rewards broad usefulness
        score = int((usage * 10) + (success_rate * 20) + (uniq * 3))

        scored.append({
            "village": village,
            "name": name,
            "usage": usage,
            "done": done,
            "uniq": uniq,
            "score": score,
            "contributors": contributors
        })

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:limit], start.split(" ")[0]
