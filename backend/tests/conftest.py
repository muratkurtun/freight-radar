"""Shared pytest setup.

Backend modules read settings at import time via `get_settings()`. The
`Settings` model marks `database_url` and `jwt_secret` required, so we
seed dummy values before any `app.*` import lands on the test process.
The dummy DATABASE_URL is never connected to — the tests that need a
session swap in a `unittest.mock.MagicMock` instead.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg2://test:test@localhost:5432/test"
)
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("OPENAI_API_KEY", "")  # keep the LLM verifier disabled
os.environ.setdefault("SCHEDULER_ENABLED", "false")

# Make `app` importable when pytest is invoked from the repo root.
BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
