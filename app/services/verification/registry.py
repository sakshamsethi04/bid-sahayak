"""Provider registry. Swap mock providers for real ones here (VERIFICATION_MODE)."""
from ...config import VERIFICATION_MODE
from . import mock_providers as mock

_MOCK = {
    "gst": mock.MockGST(), "pan": mock.MockPAN(), "udyam": mock.MockUdyam(), "debarment": mock.MockDebarment(),
    "epfo": mock.MockEPFO(), "nsic": mock.MockNSIC(), "digilocker": mock.MockDigiLocker(),
}

USED_BY = {"gst": "GST Registration", "pan": "PAN", "udyam": "Udyam / MSME", "debarment": "Blacklist / Debarment",
           "epfo": "Not in this tender", "nsic": "Not in this tender", "digilocker": "Not in this tender"}


def get(kind: str):
    if VERIFICATION_MODE != "mock":
        raise NotImplementedError("Only mock verification is available in this POC")
    return _MOCK[kind]


def describe():
    return [{"key": k, "name": p.name, "mode": p.mode, "used_for": USED_BY[k],
             "status": "Mock verification" if USED_BY[k] != "Not in this tender" else "Mock ready · not needed"}
            for k, p in _MOCK.items()]
