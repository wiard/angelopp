#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/angelopp/app"
BASE="${BASE:-http://127.0.0.1:5002/ussd}"
PHONE="${PHONE:-+31624483533}"
SID="SMOKE$(date +%s)"
TMUX_SESSION="${TMUX_SESSION:-angelopp}"

echo "== Smoke test =="
echo "BASE=$BASE"
echo "PHONE=$PHONE"
echo "SID=$SID"
echo

cd "$APP_DIR" || exit 1

echo "== 1) Python compile =="
python3 -m compileall -q . >/dev/null
echo "OK: compileall"
echo

echo "== 2) Ensure server is responding =="
# Quick health ping (root)
root_resp="$(curl -s -X POST "$BASE" -d "sessionId=$SID" -d "phoneNumber=$PHONE" -d "text=" || true)"
if [[ -z "${root_resp}" ]]; then
  echo "FAIL: empty response from server"
  exit 2
fi
if echo "$root_resp" | grep -qi "<title>500"; then
  echo "FAIL: got 500 on root"
  echo "$root_resp"
  exit 3
fi
echo "OK: server responds"
echo

post () {
  local text="$1"
  echo "---- text=$text"
  local out
  out="$(curl -s -X POST "$BASE" -d "sessionId=$SID" -d "phoneNumber=$PHONE" -d "text=$text" || true)"
  if [[ -z "$out" ]]; then
    echo "FAIL: empty response for text=$text"
    exit 10
  fi
  if echo "$out" | grep -qi "<title>500"; then
    echo "FAIL: 500 for text=$text"
    echo "$out"
    exit 11
  fi
  echo "$out"
  echo
}

echo "== 3) Core menu flows =="
post ""          # root
post "1"         # riders
post "2"         # businesses menu
post "2*1"       # village list (Bumala)
post "2*1*1"     # business detail
post "2*0"       # back to root
post "4"         # change place
post "4*1"       # choose village list
post "4*1*2"     # set village (Butula)
post ""          # root shows saved village
post "8"         # travel
post "9"         # switch role menu
echo "OK: menus"
echo

echo "== 4) Channels: create/post/listen =="
# Ensure we have a channel; if not, create it.
ch_dash="$(curl -s -X POST "$BASE" -d "sessionId=$SID" -d "phoneNumber=$PHONE" -d "text=7" || true)"
if echo "$ch_dash" | grep -qi "don.t have a channel"; then
  post "7"
  post "7*1"
  post "7*1*WiardRadio"
  post "7*1*WiardRadio*1"
else
  echo "Channel exists already."
  echo
fi

# Post a message
post "7"
post "7*1"
post "7*1*Smoke test message $(date +%H:%M:%S)"

# Listen community latest
post "6"
post "6*1"
echo "OK: channels"
echo

echo "== 5) Log sanity: check tmux for tracebacks/500 =="
if tmux has-session -t "$TMUX_SESSION" 2>/dev/null; then
  # Search recent logs for tracebacks/errors
  if tmux capture-pane -t "$TMUX_SESSION" -p -S -800 | egrep -n "Traceback|ERROR in app|Exception on /ussd|sqlite3\.OperationalError|\"POST /ussd .* 500" >/dev/null; then
    echo "FAIL: found error patterns in tmux logs:"
    tmux capture-pane -t "$TMUX_SESSION" -p -S -800 | egrep -n "Traceback|ERROR in app|Exception on /ussd|sqlite3\.OperationalError|\"POST /ussd .* 500" | tail -n 80
    exit 20
  fi
  echo "OK: no error patterns in tmux logs"
else
  echo "WARN: tmux session '$TMUX_SESSION' not found; skipping log check"
fi
echo

echo "== 6) DB sanity =="
/opt/ussd/.venv/bin/python - <<'PY'
import ussd

conn = ussd.db()
cur = conn.cursor()

cur.execute("PRAGMA database_list;")
print("DB:", [dict(r) for r in cur.fetchall()])

cur.execute("PRAGMA table_info(user_prefs);")
cols = [r[1] for r in cur.fetchall()]
print("user_prefs cols:", cols)

# show a couple prefs
cur.execute("SELECT phone, role, village FROM user_prefs ORDER BY updated_at DESC LIMIT 5;")
prefs = [dict(r) for r in cur.fetchall()]
print("prefs sample:", prefs)

# messages (schema-tolerant)
try:
    cur.execute("PRAGMA table_info(messages);")
    mcols = [r[1] for r in cur.fetchall()]
    print("messages cols:", mcols)

    def pick(*names):
        for n in names:
            if n in mcols:
                return n
        return None

    id_col      = pick("id", "msg_id")
    chan_col    = pick("channel_id", "channel")
    cat_col     = pick("category", "cat")
    phone_col   = pick("phone", "sender_phone", "from_phone", "sender", "author_phone")
    text_col    = pick("text", "message", "body")
    created_col = pick("created_at", "ts", "created")

    cols = [c for c in [id_col, chan_col, cat_col, phone_col, text_col, created_col] if c]
    if not cols:
        print("messages(last5): [] (no known cols)")
    else:
        order_col = id_col or created_col or cols[0]
        q = f"SELECT {', '.join(cols)} FROM messages ORDER BY {order_col} DESC LIMIT 5;"
        cur.execute(q)
        msgs = cur.fetchall()
        print("messages(last5):", [tuple(r) for r in msgs])
except Exception as e:
    print("messages(last5): [] (messages table missing or unreadable)", e)
PY
echo "OK: db sanity"
echo

echo "✅ SMOKE TEST PASSED"
