from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol


@dataclass
class SmsMessage:
    to_phone: str
    text: str


class SmsAdapter(Protocol):
    def send_sms(self, msg: SmsMessage) -> bool: ...


class DummySmsAdapter:
    """
    Local dev adapter: prints to stdout / logs.
    Replace with Africa's Talking SMS or another SMS provider.
    """
    def send_sms(self, msg: SmsMessage) -> bool:
        print(f"[SMS:DUMMY] to={msg.to_phone} text={msg.text}", flush=True)
        return True
