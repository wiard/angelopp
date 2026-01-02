# Sacco Architecture (Angelopp v1)

## Purpose
In Angelopp, the Sacco is the “spin in the web”:
- Knowledge center (rules, safety, procedures)
- Trust anchor (verification + dispute handling)
- Public communication channel (official updates)
- Coordination layer (issues, emergencies, community events)

## USSD Navigation (Customer)
Root:
- 5. Sacco Line ->

Sacco Line:
1. Latest Sacco updates (reads from Sacco channel)
2. Sacco principles & safety (curated, short)
3. Verified riders (PUBLIC view is always masked: Rider #XYZ)
4. Report an issue (writes to sacco_issues)
5. How Sacco supports the community (legitimacy + role explanation)
0. Back

## Privacy Rules (Hard)
- Public screens NEVER show real phone numbers for riders.
- Use masking everywhere: "Rider #XYZ".
- Internal/admin views may store full phone numbers.

## Minimal Data Model (v1)
Option A (recommended): keep flags inside existing tables.
- providers:
  - is_verified_by_sacco INTEGER DEFAULT 0
  - verified_label TEXT DEFAULT ''

Option B: separate table.
- sacco_verified_riders:
  - phone TEXT PRIMARY KEY
  - label TEXT NOT NULL
  - verified_by TEXT DEFAULT ''
  - verified_at TEXT DEFAULT (datetime('now'))
  - active INTEGER DEFAULT 1

Issues:
- sacco_issues:
  - id INTEGER PRIMARY KEY AUTOINCREMENT
  - from_phone TEXT NOT NULL
  - issue_text TEXT NOT NULL
  - created_at TEXT NOT NULL DEFAULT (datetime('now'))
  - status TEXT NOT NULL DEFAULT 'open'
  - assigned_to TEXT DEFAULT ''
  - resolution_note TEXT DEFAULT ''

## Integration with Channels
- Use category "Sacco" as the official broadcast stream.
- Latest Sacco updates screen reads channel_messages where category='Sacco'.
