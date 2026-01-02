#!/usr/bin/env bash
set -euo pipefail

URL="${URL:-https://ussd.angelopp.com/ussd}"
PHONE="${PHONE:-+31624483533}"
SESSION="${SESSION:-SIM$(date +%s)}"
TEXT=""

divider() {
  echo "============================================================"
}

post_ussd() {
  local text="${1:-}"
  # Africa's Talking sends form fields: sessionId, phoneNumber, text
  curl -s -X POST "$URL" \
    -d "sessionId=$SESSION" \
    -d "phoneNumber=$PHONE" \
    -d "text=$text"
}

strip_html() {
  # If Flask error returns HTML, show a compact hint + last lines
  local body="$1"
  if echo "$body" | grep -qi "<!doctype html"; then
    echo "[HTTP] Got HTML (probably 500/502). Showing tail:"
    echo "$body" | tail -n 25
    return 0
  fi
  echo "$body"
}

show_screen() {
  local resp="$1"
  divider
  echo "URL:      $URL"
  echo "PHONE:    $PHONE"
  echo "SESSION:  $SESSION"
  if [[ -z "$TEXT" ]]; then
    echo "TEXT:     <empty>"
  else
    echo "TEXT:     $TEXT"
  fi
  echo "------------------------------------------------------------"
  strip_html "$resp"
  divider
  echo
}

append_token() {
  local token="$1"
  if [[ -z "$TEXT" ]]; then
    TEXT="$token"
  else
    TEXT="${TEXT}*${token}"
  fi
}

pop_token() {
  if [[ -z "$TEXT" ]]; then
    return 0
  fi
  IFS='*' read -r -a parts <<< "$TEXT"
  if (( ${#parts[@]} <= 1 )); then
    TEXT=""
  else
    unset 'parts[${#parts[@]}-1]'
    TEXT="$(IFS='*'; echo "${parts[*]}")"
  fi
}

main() {
  local resp
  resp="$(post_ussd "$TEXT")"
  show_screen "$resp"

  while true; do
    echo "Input:"
    echo "  [number]  -> choose menu item (appends token)"
    echo "  t <text>  -> type free text token (name/message/etc)"
    echo "  send      -> resend current TEXT (no change)"
    echo "  b         -> back (removes last token)"
    echo "  r         -> reset (TEXT empty)"
    echo "  p         -> change phone"
    echo "  u         -> change url"
    echo "  s         -> change sessionId"
    echo "  q         -> quit"
    read -r -p "> " choice || exit 0

    # Trim
    choice="${choice#"${choice%%[![:space:]]*}"}"
    choice="${choice%"${choice##*[![:space:]]}"}"

    case "$choice" in
      q|quit)
        exit 0
        ;;
      b|back)
        pop_token
        ;;
      r|reset)
        TEXT=""
        ;;
      send)
        : # no change
        ;;
      p|phone)
        read -r -p "New PHONE (e.g. +2547...): " PHONE
        ;;
      u|url)
        read -r -p "New URL: " URL
        ;;
      s|session)
        read -r -p "New SESSION: " SESSION
        ;;
      t\ *)
        # free text token after "t "
        token="${choice#t }"
        if [[ -z "$token" ]]; then
          echo "(empty text ignored)"
        else
          append_token "$token"
        fi
        ;;
      "")
        # repeat / send without change
        :
        ;;
      *)
        # If purely digits -> menu selection token
        if [[ "$choice" =~ ^[0-9]+$ ]]; then
          append_token "$choice"
        else
          echo "Unknown input. Use a number, or: t <text>, b, r, send, p, u, s, q"
          continue
        fi
        ;;
    esac

    resp="$(post_ussd "$TEXT")"
    show_screen "$resp"
  done
}

main
