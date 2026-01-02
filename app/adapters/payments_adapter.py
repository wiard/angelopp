from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol, Optional


@dataclass
class PaymentRequest:
    phone: str
    amount_kes: int
    account_ref: str
    description: str


@dataclass
class PaymentResult:
    ok: bool
    provider_ref: Optional[str] = None
    message: str = ""


class PaymentsAdapter(Protocol):
    def initiate_stk_push(self, req: PaymentRequest) -> PaymentResult: ...
    def check_status(self, provider_ref: str) -> PaymentResult: ...


class DummyPaymentsAdapter:
    """
    Local dev adapter: always succeeds without calling real M-Pesa.
    Replace with Africa's Talking Payments / Safaricom STK Push integration.
    """
    def initiate_stk_push(self, req: PaymentRequest) -> PaymentResult:
        return PaymentResult(ok=True, provider_ref="DUMMY-STK-REF", message="Dummy payment initiated")

    def check_status(self, provider_ref: str) -> PaymentResult:
        return PaymentResult(ok=True, provider_ref=provider_ref, message="Dummy payment confirmed")
