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
