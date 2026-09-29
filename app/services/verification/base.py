"""Verification service interfaces.

Each government source is a provider with a stable interface. The POC ships MOCK
providers (mock_providers.py). To go live, implement the same methods against the
real API (GSTN, Udyam, Protean/ITD, EPFO, DigiLocker, CPPP debarment list...) and
register it in registry.py. Nothing else in the app needs to change.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class LookupResult:
    found: bool
    record: dict = field(default_factory=dict)
    source: str = ""
    mode: str = "MOCK"
    latency_ms: int = 0
    message: str = ""


class Provider(ABC):
    key: str = ""
    name: str = ""
    mode: str = "MOCK"

    @abstractmethod
    def lookup(self, identifier: str) -> LookupResult: ...


class GSTProvider(Provider):
    key, name = "gst", "GST (GSTN taxpayer search)"


class PANProvider(Provider):
    key, name = "pan", "PAN / ITR (Income Tax Dept.)"


class UdyamProvider(Provider):
    key, name = "udyam", "Udyam / MSME (Ministry of MSME)"


class DebarmentProvider(Provider):
    key, name = "debarment", "Blacklist / Debarment lists"


class EPFOProvider(Provider):
    key, name = "epfo", "EPFO / ESIC establishment search"


class NSICProvider(Provider):
    key, name = "nsic", "NSIC registration"


class DigiLockerProvider(Provider):
    key, name = "digilocker", "DigiLocker issued documents"
