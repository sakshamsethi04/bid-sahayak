"""MOCK verification providers backed by app/demo/mock_registry.json.

They behave like remote services (latency, not-found cases) but never touch a real
government system. Every result is labelled mode="MOCK" and shown as
"Mock verification" in the UI.
"""
import json
import random
import re
import time
from pathlib import Path

from .base import (DebarmentProvider, DigiLockerProvider, EPFOProvider, GSTProvider, LookupResult,
                   NSICProvider, PANProvider, UdyamProvider)

REGISTRY = json.loads((Path(__file__).resolve().parents[2] / "demo" / "mock_registry.json").read_text())


def _latency():
    ms = random.randint(120, 380)
    time.sleep(ms / 4000)  # keep the demo snappy while still reporting realistic latency
    return ms


def norm_name(s: str) -> str:
    s = s.upper().replace("PVT.", "PRIVATE").replace("PVT", "PRIVATE").replace("LTD.", "LIMITED").replace("LTD", "LIMITED")
    return re.sub(r"[^A-Z0-9]", "", s)


class MockGST(GSTProvider):
    def lookup(self, gstin):
        rec = REGISTRY["gst"].get(gstin)
        return LookupResult(bool(rec), rec or {}, "Mock GST registry", "MOCK", _latency(),
                            "" if rec else "GSTIN not found in registry")


class MockPAN(PANProvider):
    def lookup(self, pan):
        rec = REGISTRY["pan"].get(pan)
        return LookupResult(bool(rec), rec or {}, "Mock PAN/ITR registry", "MOCK", _latency())


class MockUdyam(UdyamProvider):
    def lookup(self, number):
        rec = REGISTRY["udyam"].get(number)
        return LookupResult(bool(rec), rec or {}, "Mock Udyam registry", "MOCK", _latency())


class MockDebarment(DebarmentProvider):
    def lookup(self, name):
        target = norm_name(name)
        hits = [d for d in REGISTRY["debarment"] if norm_name(d["name"]) == target]
        return LookupResult(bool(hits), {"matches": hits, "lists_checked": 3, "entries_scanned": len(REGISTRY["debarment"])},
                            "Mock debarment lists (3 sources)", "MOCK", _latency())


class MockEPFO(EPFOProvider):
    def lookup(self, identifier):
        return LookupResult(False, {}, "Mock EPFO", "MOCK", 0, "Not required by this tender")


class MockNSIC(NSICProvider):
    def lookup(self, identifier):
        return LookupResult(False, {}, "Mock NSIC", "MOCK", 0, "Not required by this tender")


class MockDigiLocker(DigiLockerProvider):
    def lookup(self, identifier):
        return LookupResult(False, {}, "Mock DigiLocker", "MOCK", 0, "Not required by this tender")
