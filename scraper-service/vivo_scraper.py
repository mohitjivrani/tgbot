import json
import logging
import re

from bs4 import BeautifulSoup

from base_scraper import BaseScraper

logger = logging.getLogger(__name__)


class VivoScraper(BaseScraper):
    def scrape(self, url: str) -> dict:
        try:
            response = self._get_with_retry(url)
            soup = BeautifulSoup(response.text, "lxml")

            product_name = self._extract_name(soup)
            price = self._extract_price(soup)
            availability = self._extract_availability(soup)

            return {
                "product_name": product_name,
                "price": price,
                "availability": availability,
                "bank_offers": [],
                "platform": "vivo",
            }
        except Exception as exc:
            logger.error("Vivo scrape failed for %s: %s", url, exc)
            return {
                "product_name": None,
                "price": None,
                "availability": None,
                "bank_offers": [],
                "platform": "vivo",
                "error": str(exc),
            }

    def _extract_name(self, soup: BeautifulSoup):
        # Try JSON-LD first
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string)
                if isinstance(data, dict) and data.get("name"):
                    return data["name"]
            except Exception:
                pass

        h1 = soup.find("h1")
        if h1:
            return h1.get_text(strip=True)

        title = soup.find("title")
        if title:
            return title.get_text(strip=True).split("|")[0].strip()

        return None

    def _extract_price(self, soup: BeautifulSoup):
        # Common patterns on Vivo IN site
        for selector in [".price", ".product-price", "[class*='price']"]:
            el = soup.select_one(selector)
            if el:
                text = el.get_text(strip=True)
                cleaned = re.sub(r"[^\d]", "", text)
                if cleaned:
                    return int(cleaned)

        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string)
                if isinstance(data, dict):
                    offers = data.get("offers", {})
                    if isinstance(offers, dict):
                        price = offers.get("price")
                        if price:
                            return int(float(str(price)))
            except Exception:
                pass

        return None

    def _extract_availability(self, soup: BeautifulSoup):
        out_of_stock = soup.find(string=re.compile(r"out of stock", re.I))
        if out_of_stock:
            return False
        buy_btn = soup.find(string=re.compile(r"buy now|add to cart", re.I))
        if buy_btn:
            return True
        return None
