"""APA_citation_finder :: utils/http.py
Rate-limited HTTP requests with retry/backoff (per-domain pacing).
"""
from __future__ import annotations

import logging
import time
from typing import Any
from urllib.parse import urlparse

import requests

logger = logging.getLogger("APA_citation_finder")
if not logger.handlers:
    h = logging.StreamHandler()
    h.setFormatter(logging.Formatter("[APA_citation_finder] %(message)s"))
    logger.addHandler(h)
    logger.setLevel(logging.INFO)

_LAST_REQUEST_TIME: dict[str, float] = {}


def rate_limited_request(
    url: str,
    params: dict | None = None,
    headers: dict | None = None,
    min_interval: float = 0.5,
    max_retries: int = 3,
    timeout: int = 25,
    method: str = "GET",
    json_body: dict | None = None,
) -> Any:
    """HTTP request with per-domain pacing and exponential backoff.

    Returns parsed JSON (dict/list), raw text for non-JSON responses, or None.
    """
    domain = urlparse(url).netloc or url
    last = _LAST_REQUEST_TIME.get(domain, 0.0)
    elapsed = time.time() - last
    if elapsed < min_interval:
        time.sleep(min_interval - elapsed)

    for attempt in range(max_retries):
        try:
            _LAST_REQUEST_TIME[domain] = time.time()
            if method == "POST":
                resp = requests.post(url, params=params, headers=headers,
                                     json=json_body, timeout=timeout)
            else:
                resp = requests.get(url, params=params, headers=headers, timeout=timeout)
            ctype = resp.headers.get("content-type", "")
            if resp.status_code == 200:
                if "application/json" in ctype or url.endswith(".json"):
                    return resp.json()
                return resp.text
            if resp.status_code == 429:
                # keyless Semantic Scholar throttles hard; give it one short
                # retry then move on — never let an optional source stall the
                # core flow for tens of seconds
                wait = 2 ** attempt
                logger.warning(f"Rate limited ({domain}), waiting {wait}s")
                time.sleep(wait)
                continue
            if resp.status_code >= 500:
                wait = 2 ** attempt
                logger.warning(f"HTTP {resp.status_code} from {domain}, retry in {wait}s")
                time.sleep(wait)
                continue
            if resp.status_code == 404:
                return None
            logger.warning(f"HTTP {resp.status_code} for {url}")
            return None
        except requests.RequestException as e:
            wait = 2 ** attempt
            logger.warning(f"Request failed: {e}, retry {attempt + 1}/{max_retries} in {wait}s")
            time.sleep(wait)
    logger.error(f"Giving up on {url} after {max_retries} retries")
    return None
