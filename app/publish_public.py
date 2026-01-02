#!/usr/bin/env python3
import os, sqlite3, hashlib, re, argparse

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

def is_category_public(con: sqlite3.Connection, category: str) -> bool:
    cat = (category or '').strip()
    cur = con.cursor()
    cur.execute("SELECT is_public FROM public_policy WHERE category=?", (cat,))
    row = cur.fetchone()
    return bool(row) and int(row[0] or 0) == 1

def publish(category: str, limit: int, since_id: int|None, dry: bool):
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    # policy gate (hard)
    if not is_category_public(con, category):
        raise SystemExit(f"Category '{category}' is not public (public_policy). Enable it first if intended.")

    where = "WHERE category=?"
    params = [category]
    if since_id is not None:
        where += " AND id > ?"
        params.append(since_id)

    # grab newest first, publish oldest-first to preserve chronology
    cur.execute(f"""
      SELECT id, channel_id, category, author_phone, text, created_at
      FROM messages
      {where}
      ORDER BY id DESC
      LIMIT ?
    """, (*params, limit))
    rows = list(cur.fetchall())
    rows.reverse()

    # skip already published by source_message_id
    to_insert = []
    for r in rows:
        mid = int(r["id"])
        cur.execute("SELECT 1 FROM public_messages WHERE source_message_id=? LIMIT 1", (mid,))
        if cur.fetchone():
            continue
        to_insert.append(r)

    if dry:
        print(f"[DRY] would publish {len(to_insert)} message(s) from category={category}")
        if to_insert:
            r = to_insert[-1]
            print("[DRY] last sample:", scrub_public_text(r["text"]))
        return

    for r in to_insert:
        mid = int(r["id"])
        author = anon_user(r["author_phone"])
        text = scrub_public_text(r["text"])
        cur.execute("""
          INSERT INTO public_messages
            (source_message_id, category, channel_id, author_anon, text, created_at, published_at, is_hidden, note)
          VALUES (?, ?, ?, ?, ?, ?, datetime('now'), 0, '')
        """, (mid, r["category"], int(r["channel_id"] or 0), author, text, r["created_at"]))
    con.commit()
    print(f"Published {len(to_insert)} message(s) to public_messages (category={category}).")

def hide(pub_id: int, note: str):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("UPDATE public_messages SET is_hidden=1, note=? WHERE id=?", (note or "", pub_id))
    con.commit()
    print(f"Hidden public_messages.id={pub_id}")

def main():
    ap = argparse.ArgumentParser(description="Explicit publish step for Angelopp public feed")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("publish", help="Publish from messages -> public_messages (scrubbed)")
    p1.add_argument("--category", required=True, help="e.g. Community")
    p1.add_argument("--limit", type=int, default=50)
    p1.add_argument("--since-id", type=int, default=None)
    p1.add_argument("--dry-run", action="store_true")

    p2 = sub.add_parser("hide", help="Hide a public message (moderation)")
    p2.add_argument("--id", type=int, required=True)
    p2.add_argument("--note", default="")

    args = ap.parse_args()
    if args.cmd == "publish":
        publish(args.category, args.limit, args.since_id, args.dry_run)
    elif args.cmd == "hide":
        hide(args.id, args.note)

if __name__ == "__main__":
    main()
