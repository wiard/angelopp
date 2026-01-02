# Africa’s Talking USSD Cost Model (Pilot-ready)

## What drives cost
USSD is typically billed per time block (often per 20 seconds) and/or per session depending on country/telco plan.
Africa’s Talking pricing mentions a "USSD Infrastructure Fee (per 20 seconds)" and also "Post-paid session costs" depending on network/telco plan.

## Pilot estimation model (always valid)
Let:
- session_seconds = average time user stays in USSD
- blocks = ceil(session_seconds / 20)
- sessions_per_day = total USSD sessions/day
- cost_per_block = your negotiated/quoted rate per 20s block (Kenya/telco specific)
Then:
- daily_cost = sessions_per_day * blocks * cost_per_block
- monthly_cost = daily_cost * 30

## Scenarios (fill in your Kenya rate)
Assume average session_seconds = 40–80s -> blocks = 2–4

LOW: 100 active users/day
- 1 session/day/user
- 2 blocks/session
=> sessions_per_day=100, blocks=2 => 200 blocks/day

MID: 300 active users/day
- 2 sessions/day/user
- 3 blocks/session
=> sessions_per_day=600, blocks=3 => 1800 blocks/day

HIGH: 500 active users/day
- 3 sessions/day/user
- 4 blocks/session
=> sessions_per_day=1500, blocks=4 => 6000 blocks/day

Monthly cost = blocks/day * cost_per_block * 30

## How Angelopp reduces cost
- Keep menus shallow (few steps)
- Keep text short
- Avoid reloading long lists
- Cache “latest updates” and show top 5
- Prefer "0. Back" loops over re-onboarding
