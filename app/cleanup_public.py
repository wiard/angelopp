#!/usr/bin/env python3
import argparse, sqlite3, datetime

def now_utc_sql():
    # SQLite datetime('now') is UTC
    return "datetime('now')"

def cleanup(db_path: str, dry_run: bool=False):
    con = sqlite3.connect(db_path)
    cur = con.cursor()

    # Hide expired items where not pinned and not already hidden
    q = f"""
    SELECT COUNT(*)
    FROM public_messages
    WHERE is_hidden=0
      AND COALESCE(is_pinned,0)=0
      AND expires_at IS NOT NULL
      AND expires_at < {now_utc_sql()}
    """
    cur.execute(q)
    n = int(cur.fetchone()[0] or 0)

    if dry_run:
        print(f"DRY RUN: would hide {n} expired public_messages")
        con.close()
        return

    cur.execute(f"""
      UPDATE public_messages
      SET is_hidden=1, note=CASE
          WHEN note='' THEN 'auto-expired'
          ELSE note || ';auto-expired'
      END
      WHERE is_hidden=0
        AND COALESCE(is_pinned,0)=0
        AND expires_at IS NOT NULL
        AND expires_at < {now_utc_sql()}
    """)
    con.commit()
    con.close()
    print(f"Hid {n} expired public_messages")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="/opt/angelopp/data/bumala.db")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    cleanup(args.db, args.dry_run)

if __name__ == "__main__":
    main()
