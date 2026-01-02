from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class Candidate:
    phone: str
    eta_minutes: Optional[float] = None
    trust_score: float = 0.5   # 0..1
    recent_jobs: int = 0       # fairness signal
    expected_income: float = 0 # optional


@dataclass
class PolicyWeights:
    w_eta: float = 1.0
    w_trust: float = 1.0
    w_fairness: float = 1.0
    w_income: float = 0.2


def _eta_score(eta_minutes: Optional[float]) -> float:
    # Lower ETA => higher score. Simple bounded mapping.
    if eta_minutes is None:
        return 0.0
    # 0 min => 1.0, 30 min => ~0.0
    return max(0.0, 1.0 - (eta_minutes / 30.0))


def _fairness_score(recent_jobs: int) -> float:
    # Fewer recent jobs => higher score (encourage distribution).
    # 0 jobs => 1.0, 10+ => 0.0
    return max(0.0, 1.0 - min(recent_jobs, 10) / 10.0)


def score_candidate(c: Candidate, w: PolicyWeights) -> float:
    return (
        w.w_eta * _eta_score(c.eta_minutes)
        + w.w_trust * float(c.trust_score)
        + w.w_fairness * _fairness_score(c.recent_jobs)
        + w.w_income * float(c.expected_income)
    )


def rank_candidates(candidates: List[Candidate], weights: Optional[PolicyWeights] = None) -> List[Candidate]:
    w = weights or PolicyWeights()
    return sorted(candidates, key=lambda c: score_candidate(c, w), reverse=True)


def explain_score(c: Candidate, w: Optional[PolicyWeights] = None) -> Dict[str, float]:
    w = w or PolicyWeights()
    return {
        "eta": w.w_eta * _eta_score(c.eta_minutes),
        "trust": w.w_trust * float(c.trust_score),
        "fairness": w.w_fairness * _fairness_score(c.recent_jobs),
        "income": w.w_income * float(c.expected_income),
        "total": score_candidate(c, w),
    }
