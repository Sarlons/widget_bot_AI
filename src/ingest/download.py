"""Tiny HTTP helper used by the ingest scripts (free public sources, no login)."""
from __future__ import annotations

import time

import requests
import truststore

# Use the Windows certificate store (like browsers and curl do). Some networks/antivirus
# add certificates that Python's bundled list does not know; verification stays ON.
truststore.inject_into_ssl()

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}  # some servers reset unusual agents


def fetch(url: str, retries: int = 3, timeout: int = 60) -> bytes:
    """Download a URL and return the raw bytes, retrying on network errors."""
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=timeout)
            r.raise_for_status()
            return r.content
        except requests.RequestException:
            if attempt == retries - 1:
                raise
            time.sleep(2 ** (attempt + 1))
    raise RuntimeError("unreachable")
