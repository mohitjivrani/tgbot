import json
import logging
import re

from bs4 import BeautifulSoup

from base_scraper import BaseScraper

logger = logging.getLogger(__name__)


class VivoScraper(BaseScraper):
    def scrape(self, url: str, pincode: str | None = None) -> dict:
        try:
            response = self._get_with_retry(url)
            soup = BeautifulSoup(response.text, "lxml")

            product_name = self._extract_name(soup)
            price = self._extract_price(soup)
            availability = self._extract_availability(soup)
            deliverable = self._extract_deliverability(soup, pincode)

            return {
                "product_name": product_name,
                "price": price,
                "availability": availability,
                "deliverable": deliverable,
                "bank_offers": [],
                "platform": "vivo",
            }
        except Exception as exc:
            logger.error("Vivo scrape failed for %s: %s", url, exc)
            return {
                "product_name": None,
                "price": None,
                "availability": None,
                "deliverable": None,
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
                parsed = self._parse_price_text(text)
                if parsed is not None:
                    return parsed

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
        for node in soup.select("button, a, [role='button']"):
            label = node.get_text(" ", strip=True)
            if not label:
                continue
            if not re.search(r"buy now|add to cart", label, re.I):
                continue

            is_disabled = (
                node.has_attr("disabled")
                or str(node.get("aria-disabled", "")).lower() == "true"
                or "disabled" in " ".join(node.get("class", [])).lower()
            )
            if not is_disabled:
                return True

        out_of_stock = soup.find(string=re.compile(r"out of stock", re.I))
        if out_of_stock:
            return False

        buy_btn = soup.find(string=re.compile(r"buy now|add to cart", re.I))
        if buy_btn:
            return True
        return None

    def _parse_price_text(self, text: str):
        if not text:
            return None

        amount_match = re.search(r"([\d,]+(?:\.\d{1,2})?)", text)
        if not amount_match:
            return None

        raw_amount = amount_match.group(1).replace(",", "")
        try:
            value = float(raw_amount)
        except ValueError:
            return None

        return int(round(value))

    def _extract_deliverability(self, soup: BeautifulSoup, pincode: str | None):
        page_text = soup.get_text(" ", strip=True)
        if not page_text:
            return None

        normalized = re.sub(r"\s+", " ", page_text).lower()
        if re.search(r"not\s+deliverable|delivery\s+not\s+available|cannot\s+be\s+delivered|unserviceable", normalized):
            return False

        if pincode:
            if re.search(rf"{re.escape(pincode)}[^.\n]{{0,40}}(not\s+deliverable|delivery\s+not\s+available|cannot\s+be\s+delivered|unserviceable)", normalized):
                return False
            if re.search(rf"{re.escape(pincode)}[^.\n]{{0,40}}(deliverable|delivery\s+available|delivery\s+by)", normalized):
                return True

        if re.search(r"delivery\s+by|delivery\s+available|deliverable", normalized):
            return True

        return None
