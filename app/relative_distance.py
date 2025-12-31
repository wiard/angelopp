"""
relative_distance.py

Berekent relatieve afstand tussen customer en driver
zonder GPS, geschikt voor USSD / feature phones.

Afstand is contextueel:
- landmark
- village
- optioneel ETA
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class PersonLocation:
    phone: str
    village: Optional[str] = None
    landmark: Optional[str] = None
    eta_minutes: Optional[int] = None


def distance_score(customer: PersonLocation, driver: PersonLocation) -> int:
    """
    Lagere score = dichterbij
    """

    score = 0

    # Zelfde landmark → heel dichtbij
    if customer.landmark and driver.landmark:
        if customer.landmark == driver.landmark:
            score += 0
        else:
            score += 5
    else:
        score += 3

    # Zelfde village → dichterbij
    if customer.village and driver.village:
        if customer.village == driver.village:
            score += 0
        else:
            score += 5
    else:
        score += 2

    # ETA verfijnt afstand (optioneel)
    if driver.eta_minutes is not None:
        score += driver.eta_minutes

    return score


def rank_drivers(customer: PersonLocation, drivers: list[PersonLocation]) -> list[PersonLocation]:
    """
    Sorteer drivers op relatieve afstand
    """
    return sorted(drivers, key=lambda d: distance_score(customer, d))
