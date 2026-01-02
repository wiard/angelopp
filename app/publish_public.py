#!/usr/bin/env python3
import argparse
import sqlite3
import hashlib
import os
import re

DB_PATH = os.environ.get("ANGELOPP_DB", "/opt/angelopp/data/bumala.db")
ANON_SALT = os.environ.get("ANGELOPP_ANON_SALT", "angelopp-public-v1")

_phone_re = re.compile(r'(?:\+?\d[\d\s\-().]{6,}\d)')
_email_re = re.compile(r'\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b', re.I)
_url_re   = re.compile(r'\bhttps?://\S+\b', re.I)

def _mask_digits(token: str) -> str:
    digits = re.sub(r'\D', '', token or '')
    if len(digits) < 7:
        return token
    return '•' * max(0, len(digits)-2) + digits[-2:]

def scrub_public_text(text: str) -> str:
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

def ttl_to_expires(ttl: str | None) -> str | None:
    """
    ttl examples:
      24h, 7d, 90d, 0 (means no expiry), none
    """
    if not ttl or ttl.lower() in ("none", "null"):
        return None
    ttl = ttl.strip().lower()
    if ttl == "0":
        return None
    # SQLite-friendly datetime add: datetime('now', '+24 hours'), '+7 days'
    if ttl.endswith("h"):
        n = int(ttl[:-1])
        return f"datetime('now','+{n} hours')"
    if ttl.endswith("d"):
        n = int(ttl[:-1])
        return f"datetime('now','+{n} days')"
    raise ValueError("Bad ttl format. Use 24h / 7d / 90d / none / 0")

def is_category_public(con, category: str) -> bool:
    cur = con.cursor()
    cur.execute("SELECT is_public FROM public_policy WHERE category=?", (category,))
    r = cur.fetchone()
    return bool(r and int(r[0] or 0) == 1)

def publish(category: str, limit: int, since_id: int|None, dry_run: bool, ttl: str|None, pin: bool):
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    # Guard: category must be public in policy
    if not is_category_public(con, category):
        print(f"Refusing: category '{category}' is not public in public_policy (set is_public=1 to allow publishing).")
        con.close()
        return

    where = "WHERE category=?"
    params = [category]
    if since_id is not None:
        where += " AND id>=?"
        params.append(since_id)

    cur.execute(f"""
      SELECT id, channel_id, category, author_phone, text, created_at
      FROM messages
      {where}
      ORDER BY id DESC
      LIMIT ?
    """, (*params, limit))
    rows = cur.fetchall()

    # If TTL specified -> compute expires SQL expression string, else default 24h for text
    expires_expr = None
    if ttl is None:
        expires_expr = "datetime('now','+24 hours')"   # default for text posts
    else:
        e = ttl_to_expires(ttl)
        expires_expr = e  # may be None

    published = 0
    for r in rows[::-1]:
        mid = int(r["id"])
        # skip if already published
        cur.execute("SELECT 1 FROM public_messages WHERE source_message_id=? LIMIT 1", (mid,))
        if cur.fetchone():
            continue

        author = anon_user(r["author_phone"] or "")
        text = scrub_public_text(r["text"] or "")

        if dry_run:
            print(f"[DRY] publish message_id={mid} -> author={author} text={text[:80]!r}")
            continue

        # expires_at: store a concrete timestamp (string) by asking SQLite to compute it
        expires_at_val = None
        if pin:
            expires_at_val = None
        elif expires_expr is None:
            expires_at_val = None
        else:
            cur.execute(f"SELECT {expires_expr}")
            expires_at_val = cur.fetchone()[0]

        cur.execute("""
          INSERT INTO public_messages
            (channel_id, category, author_anon, channel_name, text, created_at,
             source_message_id, published_at, is_hidden, note,
             media_type, media_ref, expires_at, is_pinned)
          VALUES
            (?, ?, ?, '', ?, ?, ?, datetime('now'), 0, '', 'text', '', ?, ?)
        """, (
          r["channel_id"], r["category"], author, text, r["created_at"],
          mid, expires_at_val, 1 if pin else 0
        ))
        published += 1

    con.commit()
    con.close()
    print(f"Published {published} message(s) to public_messages (category={category}).")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--category", default="Community")
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--since-id", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--ttl", default=None, help="e.g. 24h, 7d, 90d, none, 0")
    ap.add_argument("--pin", action="store_true", help="publish as pinned (never expires)")
    args = ap.parse_args()
    publish(args.category, args.limit, args.since_id, args.dry_run, args.ttl, args.pin)

if __name__ == "__main__":
    main()
