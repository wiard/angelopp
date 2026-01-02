# Fairness & Trust Policies

Angelopp’s core differentiator is *not* payments; it’s **matching with fairness & trust**.

## Inputs (examples)
- ETA / distance
- expected income (trip length, typical fare bands)
- trust score (community + sacco + history)
- fairness (recent jobs distribution)

## Output
A ranked list of candidates with an explainable score.

## Explainable scoring
Prefer simple additive scoring with weights:
`score = w_eta * eta_score + w_trust * trust_score + w_fair * fairness_score + ...`

## Governance
- Weights should be configurable locally (village/sacco rules).
- Keep a record of “why this choice happened” (audit trail).
