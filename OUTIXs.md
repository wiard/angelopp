# OUTIXs — Community Points System (v1)

OUTIXs are non-financial community points used inside Angelopp.
They reward positive participation, increase visibility, and strengthen trust —
without functioning as money or a speculative token.

OUTIXs are designed to work on **USSD-first infrastructure** and are
fully transparent, auditable, and locally governed.

---

## 1. What OUTIXs Are

OUTIXs are:

- ✅ **Non-monetary**
- ✅ **Non-transferable**
- ✅ **Non-speculative**
- ✅ **Earned through actions**
- ✅ **Visible but not tradeable**

They represent **contribution**, not ownership.

> Think of OUTIXs as *reputation energy* inside the Angelopp network.

---

## 2. What OUTIXs Are NOT

OUTIXs are **not**:

- ❌ Money
- ❌ Crypto tokens
- ❌ Wallet balances
- ❌ Exchangeable
- ❌ Promised future value

There is **no conversion** to airtime, cash, crypto, or services.

---

## 3. How OUTIXs Are Earned (Current v1 Rules)

OUTIXs are awarded automatically by the system.

### Active rules (v1):

| Action | OUTIXs |
|------|--------|
| Daily login (once per day) | +1 |
| Posting a channel message | +1 |
| Manual admin award (testing / governance) | configurable |

These rules are enforced in `ussd.py` and logged in the ledger.

---

## 4. Technical Implementation (Reality, Not Theory)

OUTIXs are stored in **SQLite**, not blockchain.

### Tables used:

#### `points_balance`
Stores current balance per phone number.

| column | meaning |
|------|--------|
| phone | user identifier |
| balance | total OUTIXs |
| updated_at | last update |

#### `points_ledger`
Immutable log of all actions.

| column | meaning |
|------|--------|
| phone | user |
| pts | points added |
| reason | action type |
| meta | context (e.g. channel) |
| created_at | timestamp |

> The ledger is append-only.  
> Balances are derived, not trusted blindly.

---

## 5. Why OUTIXs Exist

OUTIXs solve a real problem in local digital systems:

- Encourage **constructive behavior**
- Prevent spam without payments
- Reward visibility without money
- Build trust without surveillance
- Stay compatible with **USSD constraints**

They create **social gravity**, not economic pressure.

---

## 6. Governance (Current & Future)

### Current (v1 pilot)
- Rules are hardcoded
- Admin awards possible for testing
- No penalties yet

### Future (v2+ ideas)
- Sacco-governed rules
- Daily caps
- Community moderation signals
- Decay or time-based relevance
- Visibility weighting (not payment)

Governance decisions will be **local-first**.

---

## 7. OUTIXs and Channels

- Every **channel post** earns OUTIXs
- Channels increase **voice**, not power
- Visibility may later depend on:
  - activity
  - consistency
  - community trust

No channel can buy reach.

---

## 8. OUTIXs Philosophy

OUTIXs follow one core rule:

> **Value is created by participation, not possession.**

They are designed to:
- respect low-tech environments
- avoid financial risk
- remain explainable in one sentence
- never trap users

---

## 9. Status

**Version:** v1  
**Status:** Pilot-ready  
**Used in:** Angelopp USSD (Bumala pilot)  
**Ledger:** Active  
**Balance tracking:** Active  

OUTIXs are live.

---

## 10. One-Line Summary (for users)

> *OUTIXs are points you earn by helping the community — nothing to buy, nothing to sell.*
