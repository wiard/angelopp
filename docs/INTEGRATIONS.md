# Integrations (Outsourced by design)

Angelopp’s core should stay small and stable:
- USSD menu/router
- role recognition
- local rules
- fairness/trust policies
- audit trail (optional anchoring)

Everything else can be plugged in via adapters.

## Payments
Preferred: outsource to M-Pesa (STK Push) / payment provider.
Angelopp should only:
- request payment initiation
- store reference IDs
- confirm status (webhook/polling)

## Messaging (SMS/WhatsApp/Signal)
Angelopp can:
- send confirmations
- send masked-number contact instructions
- request callbacks from provider services

## Voice / Calling / IVR
Angelopp can:
- trigger callback
- play short IVR prompts
- connect customer ↔ provider (with masking)

## Storage / Anchoring
- Optional Outixs anchoring: anchor a compact hash of a completed match/ride/trip.
- Keep privacy: no raw phone numbers on-chain; use hashed identifiers.

## Suggested adapter interfaces
- `payments_adapter.py`
- `sms_adapter.py`
- `voice_adapter.py`

Each adapter should have:
- a minimal API surface
- a “dummy” implementation for local dev
- configuration via env vars
