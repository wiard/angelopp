# OUTIXs in Angelopp

OUTIXs are **recognition points** used inside Angelopp to reward useful actions and to create a transparent audit trail.
They are not money and they do not replace normal payments between people.

## Why OUTIXs exists
Angelopp needs a lightweight way to:
- reward constructive behavior (helpfulness, safety, contributions),
- record proof-of-action (who did what, when),
- strengthen local governance (especially Sacco leadership),
- support fairness and trust without heavy social-media mechanics.

## What OUTIXs is (and is not)
**OUTIXs IS:**
- a local point system (ledger-based),
- a proof-of-action log,
- a motivation and governance tool.

**OUTIXs is NOT:**
- a currency,
- a promise of cash value,
- a “pay-to-win” mechanism.

## Where OUTIXs is stored
Angelopp uses a simple SQLite model:
- `points`: current balance per phone number
- `points_ledger`: append-only record of changes (who/amount/reason/meta/time)
- optional rate-limit tables like `daily_claims`

This makes OUTIXs auditable and resilient.

## v1 rules (pilot-proof)
In v1 we keep it minimal and stable:
- **+1 OUTIXs** when someone reports a safety issue in *Sacco Line* (constructive reporting)
- **+1 OUTIXs** when someone posts a channel message (publishing useful information)

All awarding is **fail-safe**: it must never break USSD flows (no 500 errors).

## How Sacco benefits
Sacco is the “spin in the web”:
- Sacco can publish safety rules and procedures via Sacco channels
- Sacco can validate riders (verification)
- Sacco can receive issue reports and follow up
- OUTIXs can later be used to acknowledge Sacco actions and community improvements

## Future expansion (v1.1 ideas)
- extra OUTIXs for Sacco-verified updates
- OUTIXs for resolving issues (closure + confirmation)
- small “community milestones” (e.g., 30 days without major incidents)
- dashboards for Sacco leadership (offline/CLI or web)

