import json
import logging
import re

from bs4 import BeautifulSoup

from base_scraper import BaseScraper

logger = logging.getLogger(__name__)


class FlipkartScraper(BaseScraper):
    def scrape(self, url: str) -> dict:
        try:
            response = self._get_with_retry(url)
            final_url = response.url
            soup = BeautifulSoup(response.text, "lxml")

            product_name = self._extract_name(soup)
            price = self._extract_price(soup)
            availability = self._extract_availability(soup)
            bank_offers = self._extract_bank_offers(soup)

            return {
                "product_name": product_name,
                "price": price,
                "availability": availability,
                "bank_offers": bank_offers,
                "platform": "flipkart",
                "final_url": str(final_url),
            }
        except Exception as exc:
            logger.error("Flipkart scrape failed for %s: %s", url, exc)
            return {
                "product_name": None,
                "price": None,
                "availability": None,
                "bank_offers": [],
                "platform": "flipkart",
                "error": str(exc),
            }

    def _extract_name(self, soup: BeautifulSoup):
        # JSON-LD
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string)
                if isinstance(data, dict) and data.get("name"):
                    return data["name"]
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict) and item.get("name"):
                            return item["name"]
            except Exception:
                pass

        # Fallback: H1 or title
        h1 = soup.find("h1")
        if h1:
            return h1.get_text(strip=True)

        title = soup.find("title")
        if title:
            return title.get_text(strip=True).split("|")[0].strip()

        return None

    def _extract_price(self, soup: BeautifulSoup):
        # Common Flipkart price class selectors
        for selector in ["._30jeq3", "._1_WHN1", ".Nx9bqj", "._16Jk6d"]:
            el = soup.select_one(selector)
            if el:
                text = el.get_text(strip=True)
                cleaned = re.sub(r"[^\d]", "", text)
                if cleaned:
                    return int(cleaned)

        # JSON-LD fallback
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string)
                offers = None
                if isinstance(data, dict):
                    offers = data.get("offers")
                if offers and isinstance(offers, dict):
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
        add_to_cart = soup.find(string=re.compile(r"add to cart", re.I))
        buy_now = soup.find(string=re.compile(r"buy now", re.I))
        if add_to_cart or buy_now:
            return True
        return None

    def _extract_bank_offers(self, soup: BeautifulSoup):
        offers = []
        # Look for offer sections by common class names
        offer_sections = soup.select(".XBEQ60, ._3xFhiH, .A6+aMw, [class*='offer']")
        for section in offer_sections[:10]:
            text = section.get_text(separator=" ", strip=True)
            if not text:
                continue
            bank_match = re.search(
                r"(HDFC|SBI|ICICI|Axis|Kotak|RBL|IDFC|IndusInd|Yes Bank|AU Bank|BOB)",
                text,
                re.I,
            )
            if not bank_match:
                continue
            bank_name = bank_match.group(1).upper()

            card_match = re.search(r"(credit|debit)", text, re.I)
            card_type = card_match.group(1).capitalize() if card_match else None

            discount_match = re.search(r"₹\s*([\d,]+)", text)
            discount_value = (
                int(discount_match.group(1).replace(",", "")) if discount_match else None
            )

            min_match = re.search(r"min(?:imum)?\s+(?:transaction|purchase|order)?\s*(?:of\s*)?₹\s*([\d,]+)", text, re.I)
            min_amount = int(min_match.group(1).replace(",", "")) if min_match else None

            offers.append(
                {
                    "bank_name": bank_name,
                    "card_type": card_type,
                    "discount_value": discount_value,
                    "min_transaction_amount": min_amount,
                }
            )
        return offers
