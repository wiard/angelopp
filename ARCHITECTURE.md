# Angelopp Architecture

Angelopp is lokale digitale infrastructuur (USSD-first) die **rol-aware** menu’s aanbiedt en afspraken/matches kan vastleggen (optioneel met Outixs anchoring).  
De kernfilosofie: **Angelopp orchestrates, partners execute.**

---

## Goals

- **USSD-first**: werkt op elke telefoon.
- **Local ownership**: dorpsregels, sacco-afspraken, governance blijven lokaal.
- **Trust & fairness**: matching is niet alleen “dichtstbij”, maar een gecombineerde waarde-afweging.
- **Replaceable integrations**: betalingen/voice/sms kunnen wisselen zonder core te herschrijven.

---

## High-level Components

### 1) Interface Layer (USSD)
- Inkomende requests komen binnen via Africa’s Talking (of later Safaricom direct).
- Angelopp retourneert altijd één string-response: `CON ...` of `END ...`.

**Entry point**
- `app/app.py` – Flask `/ussd` endpoint (HTTP POST)
- `app/ussd.py` – router + menu flows

### 2) Core Logic (Menus + Policies)
- Menu logica (root menus per rol)
- Context-flow per gebruiker (village/landmark, drafts)
- Policy hooks voor fairness & trust

**Belangrijk principe**
- Alle keuzes zijn te herleiden tot simpele tokens in `text` (bijv. `9*2`, `8*1*bumalala*kisumu`).

### 3) State & Persistence
Angelopp bewaart minimale, functionele data:
- **Role per phone** (customer/provider) – persistent
- **Location** (village + landmark) – persistent
- **Drafts** (trip draft, request flow) – eventueel later persistent

Database:
- SQLite (bijv. `app/bumala.db`) via `db()` + `ensure_schema()`.

### 4) Network / Integrations (Outsourced by design)
Angelopp wil deze dingen **niet zelf** “hard” implementeren, maar via adapters/partners:

- Payments (M-Pesa / STK Push)
- SMS delivery / callbacks
- Voice / IVR / calling
- (Optioneel) identity verification

Angelopp behoudt wél:
- menu-flow
- matching-logica
- lokale regels
- fairness/trust policies
- audit trail (optioneel anchoring)

---

## Roles & Menus

### Role Recognition (per phone)
- Rol wordt opgeslagen per `phoneNumber` (persistent).
- Nieuwe sessie gebruikt automatisch de laatst gekozen rol.
- De gebruiker kan altijd wisselen via **Switch role**.

Mechanisme:
- `get_user_role(phone)` → `"customer"` of `"provider"`
- `set_user_role(phone, role)` → schrijft naar `user_prefs`

### Customer
- Find rider
- Businesses
- Register
- Change place
- Listen / channel
- **Travel** (sub-menu voor trips)

### Service Provider
- Provider acties (later: availability, accept requests, profile)
- Zelfde basisopties, maar andere defaults/acties

---

## Routing Model

USSD input komt binnen als:
- `text=""` → root menu
- `text="1*2*3"` → tokens

Router doet:
1. `parts = parse_text(text)`
2. check “global actions” (back/exit/role switch)
3. dispatch naar handler per menu-branch

Voorbeeld:
- `parts[0] == "9"` → role switch
- `parts[0] == "8"` → travel submenu

---

## Fairness & Trust (Policy Hooks)

Angelopp’s matching is bedoeld als gecombineerde waarde-afweging, bv:
- distance / ETA
- expected yield (inkomen)
- trust / safety score
- fairness (spreiding van werk)

In code komt dit als:
- `score_candidate(provider, context) -> float`
- `rank_candidates(list)`

Doel: **geen black-box**; simpele, uitlegbare regels.

---

## Outixs Anchoring (Optional)

Wanneer “afspraak/match” belangrijk is:
- Angelopp maakt een compact bewijs-object (zonder privacy-leaks)
- Hash / reference kan geankerd worden via Outixs

Dit is optioneel en moduleerbaar: core blijft werken zonder anchoring.

---

## Files (Current)

- `app/app.py` — Flask entrypoint `/ussd`
- `app/ussd.py` — menus + routing + persistence helpers
- `app/simulate_at.sh` — lokale simulator (AT simulator vervangen)
- `app/*.py` — helpers (onboarding, distances, etc.)
- `web/` — landing / uitleg

---

## Next Steps

1. **Adapters**: `payments_adapter.py`, `sms_adapter.py`, `voice_adapter.py` (stub interfaces)
2. **Policy Engine**: `fairness.py` met score/ranking functions
3. **Provider ops**: availability, accept/deny request, sacco oversight
4. **Travel**: trip drafts opslaan + opties (time/budget) + transport matching
