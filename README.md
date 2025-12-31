# Angelopp (USSD) + Outixs Anchoring

This repository contains the Angelopp USSD backend used in the Bumala pilot, with a minimal integration to anchor completed rides into an Outixs node.

## What works now

- USSD flows for customers and service providers
- Providers can complete a job (complete_job)
- On job completion, a RIDE_COMPLETED event is anchored into Outixs
- Angelopp never fails if Outixs is down (fail-safe)

## Example Outixs row

- transition_type: RIDE_COMPLETED
- internal_id: angelopp_req_3
- rider_phone: +254700000001

## Configuration

```bash
export OUTIXS_URL="http://127.0.0.1:8080"
```

## Vision

Angelopp makes local economic activity visible via USSD, and anchors it into a verifiable event stream with Outixs.

The goal is not to control, but to make agreements and real-world actions transparent and fair.

Outixs acts as a minimal, immutable memory layer for local governance and trust.
