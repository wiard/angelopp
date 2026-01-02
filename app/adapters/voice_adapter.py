from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol, Optional


@dataclass
class VoiceCallRequest:
    from_phone: str
    to_phone: str
    reason: str = ""
    masked: bool = True


@dataclass
class VoiceCallResult:
    ok: bool
    call_id: Optional[str] = None
    message: str = ""


class VoiceAdapter(Protocol):
    def request_callback(self, req: VoiceCallRequest) -> VoiceCallResult: ...


class DummyVoiceAdapter:
    """
    Local dev adapter: does not call anyone, just returns a fake call id.
    Replace with Africa's Talking Voice / IVR / callback.
    """
    def request_callback(self, req: VoiceCallRequest) -> VoiceCallResult:
        return VoiceCallResult(ok=True, call_id="DUMMY-CALL-ID", message="Dummy callback requested")
