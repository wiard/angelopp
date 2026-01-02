# Security & Privacy (Angelopp)

## Threat model (practical)
- Phone numbers are sensitive.
- USSD sessions can be replayed by attackers if exposed.
- External callers may probe endpoints.

## Principles
1. **Data minimization**: store only what you need.
2. **Masking by default**: do not reveal direct phone numbers when possible.
3. **Explainable policies**: fairness/trust should be auditable and local.
4. **Secure configs**: secrets in env vars, never in git.

## Recommended safeguards
- Rate limit `/ussd` endpoint (nginx limit_req)
- Validate `phoneNumber`, `text` size, tokens, allowed chars
- Avoid returning stack traces to USSD callers
- Log minimal: do not log full text tokens if they contain names/messages

## Masked contact pattern (future)
- Customer requests a rider
- Angelopp triggers “callback” or relays contact via masked numbers
- Sacco oversight can be integrated as local governance
