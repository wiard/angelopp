#!/usr/bin/env bash
set -euo pipefail

echo "== Smoke test =="
BASE="${BASE:-http://127.0.0.1:5002/ussd}"
PHONE="${PHONE:-+31624483533}"
SID="SMOKE$(date +%s)"
TMUX_SESSION="${TMUX_SESSION:-angelopp}"

echo "BASE=$BASE"
echo "PHONE=$PHONE"
echo "SID=$SID"
echo

curl_post () {
  local text="$1"
  echo "---- text=$text"
  # hard timeouts + retry
  curl -sS \
    --connect-timeout 2 \
    --max-time 8 \
    --retry 2 \
    --retry-delay 1 \
    -X POST "$BASE" \
    -d "sessionId=$SID" \
    -d "phoneNumber=$PHONE" \
    -d "text=$text"
  echo
  echo
}

fail_with_logs () {
  echo "FAIL: $1"
  echo
  if tmux has-session -t "$TMUX_SESSION" 2>/dev/null; then
    echo "== Last tmux logs (tail) =="
    tmux capture-pane -t "$TMUX_SESSION" -p -S -200 | tail -n 200 || true
    echo
  else
    echo "WARN: tmux session '$TMUX_SESSION' not found"
  fi
  exit 1
}

echo "== 1) Python compile =="
python3 -m compileall -q /opt/angelopp/app || fail_with_logs "compileall failed"
echo "OK: compileall"
echo

echo "== 2) Ensure server is responding =="
# quick ping (POST with empty text)
if ! curl -sS --connect-timeout 2 --max-time 5 -X POST "$BASE" \
    -d "sessionId=$SID" -d "phoneNumber=$PHONE" -d "text=" >/dev/null; then
  fail_with_logs "server not responding at $BASE"
fi
echo "OK: server responds"
echo

echo "== 3) Core menu flows =="
curl_post ""
curl_post "1"
curl_post "2"
curl_post "2*1"
curl_post "2*1*1"
curl_post "2*0"
curl_post "4"
curl_post "4*1"
curl_post "4*1*2"
curl_post ""
curl_post "8"
curl_post "9"
echo "OK: menus"
echo

echo "== 4) Channels: create/post/listen =="
# My channel dashboard
ch_dash="$(curl -sS --connect-timeout 2 --max-time 8 -X POST "$BASE" \
  -d "sessionId=$SID" -d "phoneNumber=$PHONE" -d "text=7" || true)"
echo "---- text=7"
echo "$ch_dash"
echo

if echo "$ch_dash" | grep -qi "don.t have a channel"; then
  curl_post "7"
  curl_post "7*1"
  curl_post "7*1*WiardRadio"
  curl_post "7*1*WiardRadio*1"
else
  echo "Channel exists already."
  echo
fi

curl_post "7"
curl_post "7*1"
curl_post "7*1*Smoke test message $(date +%H:%M:%S)"
curl_post "6"
curl_post "6*1"
echo "OK: channels"
echo

echo "== 5) Log sanity: check tmux for tracebacks/500 =="
if tmux has-session -t "$TMUX_SESSION" 2>/dev/null; then
  if tmux capture-pane -t "$TMUX_SESSION" -p -S -800 | \
    egrep -n 'Traceback|ERROR in app|Exception on /ussd|sqlite3\.OperationalError|"POST /ussd .* 500' >/dev/null; then
    echo "FAIL: found error patterns in tmux logs:"
    tmux capture-pane -t "$TMUX_SESSION" -p -S -800 | \
      egrep -n 'Traceback|ERROR in app|Exception on /ussd|sqlite3\.OperationalError|"POST /ussd .* 500' | tail -n 80
    exit 20
  fi
  echo "OK: no error patterns in tmux logs"
else
  echo "WARN: tmux session '$TMUX_SESSION' not found; skipping log check"
fi
echo

echo "== 6) DB sanity =="
(
  cd /opt/angelopp/app || exit 1
  /opt/ussd/.venv/bin/python - <<'PY'
import ussd
conn = ussd.db()
cur = conn.cursor()
cur.execute("PRAGMA database_list;")
print("DB:", [dict(r) for r in cur.fetchall()])
cur.execute("PRAGMA table_info(user_prefs);")
print("user_prefs cols:", [r[1] for r in cur.fetchall()])
cur.execute("SELECT * FROM user_prefs LIMIT 3;")
rows = cur.fetchall() or []
out = []
for r in rows:
    try:
        out.append(dict(r))
    except Exception:
        out.append(tuple(r))
print("prefs sample:", out)
cur.execute("SELECT name FROM sqlite_master WHERE type=\"table\" ORDER BY 1;")
tables = [r[0] for r in cur.fetchall()]
print("tables:", tables)
if "messages" in tables:
    try:
        cur.execute("SELECT * FROM messages ORDER BY id DESC LIMIT 5;")
        m = cur.fetchall() or []
        print("messages(last5):", [tuple(x) for x in m])
    except Exception as e:
        print("messages check skipped:", e)
PY
)

echo
echo "OK: DB sanity"
echo
echo "== ALL OK =="
