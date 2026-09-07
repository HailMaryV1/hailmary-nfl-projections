"""Shared .env loader + DB connection helper for every script in this
directory. Ported verbatim from dreamteam-projections/scripts/env_utils.py -
same fix applies here (Windows console can't encode arbitrary real player-
name Unicode and crashes on print() rather than mangling the glyph)."""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def load_env():
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def db_connect():
    import psycopg2

    load_env()
    return psycopg2.connect(os.environ["DATABASE_URL"])
