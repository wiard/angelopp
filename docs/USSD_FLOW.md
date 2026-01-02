# USSD Flow (Angelopp)

## Basics
Africa’s Talking (AT) sends POST to `/ussd` with:
- `sessionId`
- `phoneNumber`
- `text` (tokens like `1*2*3`)

Angelopp returns:
- `CON ...` to continue
- `END ...` to end

## Token model
User navigation is represented as `text`:
- Root: `text=""`
- Choice: `text="9"` (Switch role)
- Next: `text="9*2"` (set provider)

Your local simulator (`app/simulate_at.sh`) keeps a constant `sessionId` and builds `text` automatically.

## Global actions
Recommended global actions available in any menu:
- `0` → Back (remove last token)
- `9` → Switch role (customer/provider)
- `END` options when needed

## Current root menus
### Customer
- 1 Find Rider
- 2 Local Businesses
- 3 Register
- 4 Change place
- 6 Listen (channels)
- 7 My channel
- 8 Travel
- 9 Switch role

### Service Provider
- Provider-oriented home menu (availability/requests later)
- Switch role always available

## Notes
- Role is persisted per phone (not per session)
- Location can be persisted per phone
- Draft flows (Travel draft, request draft) can be session-based or persisted later
