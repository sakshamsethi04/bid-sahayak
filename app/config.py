"""Runtime configuration, read from environment variables (see .env.example)."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("BIDSAHAYAK_DATA_DIR", BASE_DIR / "data"))
UPLOAD_DIR = DATA_DIR / "uploads"
DEMO_DIR = BASE_DIR / "app" / "demo" / "files"
FRONTEND_DIST = BASE_DIR.parent / "frontend" / "dist"

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR / 'bidsahayak.db'}")

# Optional LLM. The app is fully functional without it (deterministic mode).
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "").lower()  # "openai" | "anthropic" | ""
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "")

# OCR: used automatically for images and for PDF pages without a text layer.
OCR_ENABLED = os.getenv("OCR_ENABLED", "true").lower() == "true"

# Verification mode. Only "mock" is implemented in this POC.
VERIFICATION_MODE = os.getenv("VERIFICATION_MODE", "mock")

for d in (DATA_DIR, UPLOAD_DIR):
    d.mkdir(parents=True, exist_ok=True)


def llm_enabled() -> bool:
    return bool(LLM_PROVIDER and LLM_API_KEY)
