# Angelopp (USSD) + Outixs Anchoring

This repository contains the Angelopp USSD backend used in the Bumala pilot,
with a minimal integration to anchor completed rides into an Outixs node.

## What works now

- USSD flows for customers and service providers
- Providers can complete a job (`complete_job`)
- On job completion, a `RIDE_COMPLETED` event is anchored into Outixs
- Each anchor includes:
  - a stable `internal_id` (`angelopp_req_<request_id>`)
  - the `rider_phone` (provider phone number)

## Example Outixs row

- `transition_type`: `RIDE_COMPLETED`
- `internal_id`: `angelopp_req_3`
- `rider_phone` : `+254700000001`

## Configuration

```bash
export OUTIXS_URL="http://127.0.0.1:8080"
```

## Code structure

- `app/angelopp_core.py` — core USSD logic + Outixs integration
- `app/angelopp.py` –  thin compatibility shim (re-export)
- `app/ussd.py` – USSD menu flows

## Design principle

Angelopp must never fail if Outixs is unavailable.
Anchoring is best-effort and non-blocking.
