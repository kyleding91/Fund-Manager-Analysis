"""Phase 1 — Download 13F filings from SEC EDGAR.

Responsibilities:
  * Fetch the quarterly form index and find every 13F-HR / 13F-HR/A filing.
  * Download each filing's full submission text (and cache it locally).
  * Be a good EDGAR citizen: descriptive User-Agent + polite rate limiting + retries.
"""
from __future__ import annotations

import time
import gzip
import logging
from dataclasses import dataclass
from pathlib import Path

import requests

from . import config

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class FilingRef:
    """A pointer to one filing found in the quarterly index."""
    form_type: str
    company: str
    cik: str
    date_filed: str          # YYYY-MM-DD
    txt_path: str            # e.g. edgar/data/1067983/0000950123-25-005701.txt

    @property
    def accession(self) -> str:
        """The accession number, e.g. 0000950123-25-005701."""
        return Path(self.txt_path).stem

    @property
    def url(self) -> str:
        return f"{config.EDGAR_BASE}/{self.txt_path}"

    @property
    def cache_path(self) -> Path:
        return config.RAW_DIR / self.cik / f"{self.accession}.txt"


class EdgarClient:
    """A thin, rate-limited HTTP client for EDGAR."""

    def __init__(self, rps: float | None = None):
        self.session = requests.Session()
        self.session.headers.update(
            {"User-Agent": config.USER_AGENT, "Accept-Encoding": "gzip, deflate"}
        )
        self._min_interval = 1.0 / (rps or config.REQUESTS_PER_SECOND)
        self._last_request = 0.0

    # -- low level ---------------------------------------------------------
    def _throttle(self) -> None:
        wait = self._min_interval - (time.monotonic() - self._last_request)
        if wait > 0:
            time.sleep(wait)
        self._last_request = time.monotonic()

    def get(self, url: str) -> bytes:
        """GET with throttling + retries. Returns raw bytes."""
        last_err: Exception | None = None
        for attempt in range(1, config.MAX_RETRIES + 1):
            self._throttle()
            try:
                resp = self.session.get(url, timeout=config.REQUEST_TIMEOUT)
                if resp.status_code == 200:
                    return resp.content
                # Back off and retry on rate-limiting / transient errors. The SEC
                # returns 403 "Request Rate Threshold Exceeded" when an IP (e.g. a
                # shared CI runner) is over the limit, so 403 is retryable too.
                # Other 4xx (404 etc.) are genuine — give up early.
                if resp.status_code in (403, 429, 503):
                    last_err = RuntimeError(f"HTTP {resp.status_code} for {url}")
                elif 400 <= resp.status_code < 500:
                    raise RuntimeError(f"HTTP {resp.status_code} for {url}")
                else:
                    last_err = RuntimeError(f"HTTP {resp.status_code} for {url}")
            except requests.RequestException as exc:
                last_err = exc
            backoff = min(2 ** attempt, 30)
            log.warning("retry %d/%d for %s (%s)", attempt, config.MAX_RETRIES, url, last_err)
            time.sleep(backoff)
        raise RuntimeError(f"Failed to GET {url}: {last_err}")

    def get_text(self, url: str) -> str:
        data = self.get(url)
        if data[:2] == b"\x1f\x8b":          # gzip magic, just in case
            data = gzip.decompress(data)
        return data.decode("latin-1")        # EDGAR text is latin-1 safe

    # -- high level --------------------------------------------------------
    def quarterly_filings(self, year: int, quarter: int) -> list[FilingRef]:
        """Return every 13F-HR / 13F-HR/A FilingRef for the given quarter."""
        url = config.FULL_INDEX_URL.format(year=year, quarter=quarter)
        log.info("Fetching quarterly index %s", url)
        text = self.get_text(url)
        refs: list[FilingRef] = []
        for line in text.splitlines():
            # Rows look like:
            # 13F-HR   COMPANY NAME ...   CIK   YYYY-MM-DD   edgar/data/.../acc.txt
            if not (line.startswith("13F-HR") or line.startswith("13F-HR/A")):
                continue
            parts = line.split()
            form_type = parts[0]
            if form_type not in config.FORM_TYPES:
                continue
            txt_path = parts[-1]
            date_filed = parts[-2]
            cik = parts[-3]
            # Company name = everything between the form type and the date column,
            # minus the trailing CIK token. We locate the date by position because
            # the CIK can also appear inside the file path (edgar/data/<cik>/...).
            date_pos = line.rfind(date_filed)
            company = " ".join(line[len(form_type):date_pos].split()[:-1])
            refs.append(FilingRef(form_type, company, cik, date_filed, txt_path))
        log.info("Found %d 13F filings for %dQ%d", len(refs), year, quarter)
        return refs

    def fetch_submission(self, ref: FilingRef, use_cache: bool = True) -> str:
        """Download (or load from cache) the full submission text for a filing."""
        cache = ref.cache_path
        if use_cache and cache.exists():
            return cache.read_text(encoding="latin-1")
        text = self.get_text(ref.url)
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(text, encoding="latin-1")
        return text
