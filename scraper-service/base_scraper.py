import logging
import time
from abc import ABC, abstractmethod

import requests

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-IN,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


class BaseScraper(ABC):
    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    @abstractmethod
    def scrape(self, url: str, pincode: str | None = None) -> dict:
        """Scrape the given URL and return structured product data."""

    def _get_with_retry(self, url: str, max_retries: int = 3) -> requests.Response:
        if max_retries < 1:
            max_retries = 1
        last_exc: Exception = RuntimeError(f"No attempts made for {url}")
        for attempt in range(max_retries):
            try:
                response = self.session.get(url, timeout=self.timeout, allow_redirects=True)
                response.raise_for_status()
                return response
            except requests.RequestException as exc:
                last_exc = exc
                wait = 2 ** attempt
                logger.warning(
                    "Request failed (attempt %d/%d) for %s: %s – retrying in %ds",
                    attempt + 1,
                    max_retries,
                    url,
                    exc,
                    wait,
                )
                time.sleep(wait)
        raise last_exc
