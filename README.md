# Angelopp (USSD) + Outixs Anchoring

Angelopp is a USSD-first local infrastructure system designed for rural and low-connectivity environments.

It makes real economic activity visible via a SINGLE USSD number, and anchors key events into an immutable outixs ledger.

## What works now

- USSD flows for customers and providers
- Providers can complete a job (`complete_job`)
- On completion, a `RIDE_COMPLETED` event is anchored into Outixs
- Each anchor includes:
  - `stable internal_id` (`angelopp_req_<REQID>`)
  - `rider_phone` (provider phone number)

## Example Outixs row

- `transition_type` : `RIDE_COMPLETED`
- `internal_id` : `angelopp_req_3`
- `rider_phone` : `+254700000001`

## Configuration

Set the Outixs endpoint used for anchoring:

```bash
export OUTIXS_URL="http://127.0.0.1:8080"
```

## Vision

Angelopp is built for communities where trust is social before it is digital.

- Technology supports real-world agreements
- USSD is a strength, not a limitation
- Blockchain is memory, not control

Together, Angelopp and Outixs create a verifiable, non-extractive digital infrastructure for local governance, fairness, and growth.

## Angelopp Core – Responsibilities

Angelopp is **lokale digitale infrastructuur**, geen platform.
De core doet bewust alleen wat lokaal, eerlijk en transparant moet zijn.

### What Angelopp Core Handles

**Menu logic**
- USSD menu’s en flows
- Context-aware navigatie (waar was de gebruiker?)

**Role recognition**
- Customer / Service Provider / Traveler
- Rol wordt onthouden per telefoonnummer
- Gebruiker kan rol altijd wisselen

**State & context**
- Sessies (USSD)
- Persistente context (rol, village, landmark)
- Concepten zoals “draft trip” of “pending request”

**Local rules**
- Dorpsregels (zones, tijden, type service)
- Sacco- of community-afspraken
- Geen centrale algoritmes

**Fairness & trust**
- Matching op meer dan afstand:
  ETA, veiligheid, vertrouwen, fairness
- Basis reputatie (lichtgewicht, USSD-proof)
- Community oversight mogelijk

**Proof & anchoring (Outixs)**
- Matches en afspraken kunnen geankerd worden
- Bewijs zonder gevoelige data
- Voor transparantie en vertrouwen

### What Angelopp Intentionally Outsources

- Payments (e.g. M-Pesa, STK Push)
- SMS delivery & callbacks
- Voice / IVR / calls
- Identity verification (optioneel)

Angelopp **orchestrates**, partners **execute**.

This keeps the system:
- Simple
- Replaceable
- Locally owned
- Scalable across villages
