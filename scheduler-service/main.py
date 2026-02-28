import hashlib
import json
import logging
import os
import time
from datetime import datetime

import httpx
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

CHECK_INTERVAL_MINUTES = int(os.getenv("CHECK_INTERVAL_MINUTES", "5"))
CHECK_INTERVAL_SECONDS = int(
    os.getenv("CHECK_INTERVAL_SECONDS", str(CHECK_INTERVAL_MINUTES * 60))
)
API_GATEWAY_URL = os.getenv("API_GATEWAY_URL", "http://api-gateway:7500")
SCRAPER_URL = os.getenv("SCRAPER_SERVICE_URL", "http://scraper-service:7501")
OFFER_ENGINE_URL = os.getenv("OFFER_ENGINE_URL", "http://offer-engine:7502")
BOT_NOTIFY_URL = os.getenv("BOT_NOTIFY_URL", "http://bot-service:8080/notify")

HTTP_TIMEOUT = 30
MAX_RETRIES = 3


def http_post_with_retry(url: str, payload: dict) -> httpx.Response:
    last_exc = None
    for attempt in range(MAX_RETRIES):
        try:
            with httpx.Client(timeout=HTTP_TIMEOUT) as client:
                resp = client.post(url, json=payload)
                resp.raise_for_status()
                return resp
        except httpx.HTTPError as exc:
            last_exc = exc
            wait = 2 ** attempt
            logger.warning("POST %s failed (attempt %d/%d): %s – retry in %ds", url, attempt + 1, MAX_RETRIES, exc, wait)
            time.sleep(wait)
    raise last_exc


def http_get_with_retry(url: str, params: dict = None) -> httpx.Response:
    last_exc = None
    for attempt in range(MAX_RETRIES):
        try:
            with httpx.Client(timeout=HTTP_TIMEOUT) as client:
                resp = client.get(url, params=params)
                resp.raise_for_status()
                return resp
        except httpx.HTTPError as exc:
            last_exc = exc
            wait = 2 ** attempt
            logger.warning("GET %s failed (attempt %d/%d): %s – retry in %ds", url, attempt + 1, MAX_RETRIES, exc, wait)
            time.sleep(wait)
    raise last_exc


def check_products():
    logger.info("Starting product check cycle...")
    try:
        resp = http_get_with_retry(f"{API_GATEWAY_URL}/products")
        products = resp.json()
    except Exception as exc:
        logger.error("Failed to fetch products from API gateway: %s", exc)
        return

    logger.info("Checking %d product(s)", len(products))

    for product in products:
        product_id = product.get("id")
        url = product.get("product_url")
        platform = product.get("platform")
        previous_hash = product.get("last_offer_hash")
        user_id = product.get("user_id")
        preferred_pincode = product.get("preferred_pincode")

        logger.info("Checking product id=%s url=%s", product_id, url)

        # Step 1: Scrape
        try:
            scrape_resp = http_post_with_retry(
                f"{SCRAPER_URL}/scrape",
                {"url": url, "platform": platform, "pincode": preferred_pincode},
            )
            scrape_data = scrape_resp.json()
        except Exception as exc:
            logger.error("Scrape failed for product id=%s: %s", product_id, exc)
            continue

        bank_offers = scrape_data.get("bank_offers", [])
        new_price = scrape_data.get("price")
        new_name = scrape_data.get("product_name")
        new_availability = scrape_data.get("availability")
        new_deliverable = scrape_data.get("deliverable")

        # Step 2: Analyze offers
        try:
            analyze_resp = http_post_with_retry(
                f"{OFFER_ENGINE_URL}/analyze",
                {"offers": bank_offers, "previous_hash": previous_hash},
            )
            analyze_data = analyze_resp.json()
        except Exception as exc:
            logger.error("Offer analysis failed for product id=%s: %s", product_id, exc)
            analyze_data = {"changed": False, "new_hash": previous_hash, "normalized_offers": []}

        changed = analyze_data.get("changed", False)
        new_hash = analyze_data.get("new_hash")
        change_type = analyze_data.get("change_type")
        normalized_offers = analyze_data.get("normalized_offers", [])

        # Build bank_offers for update (add offer_hash field)
        offers_for_update = []
        for offer in normalized_offers:
            offer_hash = hashlib.sha256(
                json.dumps(offer, sort_keys=True).encode()
            ).hexdigest()
            offers_for_update.append({**offer, "offer_hash": offer_hash})

        # Step 3: Update product in API gateway
        price_changed = new_price is not None and new_price != product.get("last_price")
        availability_changed = (
            new_availability is not None
            and new_availability != product.get("last_availability")
        )
        deliverability_changed = (
            new_deliverable is not None
            and new_deliverable != product.get("last_deliverable")
        )

        patch_payload = {
            "last_offer_hash": new_hash,
            "bank_offers": offers_for_update,
        }
        if new_name:
            patch_payload["product_name"] = new_name
        if new_price is not None:
            patch_payload["last_price"] = new_price
        if new_availability is not None:
            patch_payload["last_availability"] = new_availability
        if new_deliverable is not None:
            patch_payload["last_deliverable"] = new_deliverable
        if new_availability is True:
            patch_payload["last_available_at"] = datetime.utcnow().isoformat()
            if new_price is not None:
                patch_payload["last_available_price"] = new_price

        try:
            with httpx.Client(timeout=HTTP_TIMEOUT) as client:
                client.patch(f"{API_GATEWAY_URL}/products/{product_id}", json=patch_payload)
        except Exception as exc:
            logger.error("Failed to update product id=%s: %s", product_id, exc)

        # Step 4: Notify user if something changed
        if not (changed or price_changed or availability_changed or deliverability_changed):
            continue

        # Build notification message
        parts = [f"🔔 Update for product: {new_name or url}"]
        if price_changed:
            old_price = product.get("last_price")
            old_price_str = f"₹{old_price}" if old_price is not None else "N/A"
            parts.append(f"💰 Price: {old_price_str} → ₹{new_price}")
        if availability_changed:
            status = "✅ In Stock" if new_availability else "❌ Out of Stock"
            parts.append(f"📦 Availability: {status}")
        if deliverability_changed:
            if preferred_pincode:
                status = "✅ Deliverable" if new_deliverable else "❌ Not deliverable"
                parts.append(f"🚚 Deliverability ({preferred_pincode}): {status}")
            else:
                status = "✅ Deliverable" if new_deliverable else "❌ Not deliverable"
                parts.append(f"🚚 Deliverability: {status}")
        if changed and change_type not in (None, "INITIAL_FETCH"):
            parts.append(f"🏦 Bank offers changed ({change_type})")
        parts.append(f"🔗 Link: {url}")
        notification_text = "\n".join(parts)

        # Resolve chat_id via /users/{user_id} endpoint
        # (Telegram user IDs == chat IDs for private chats)
        telegram_user_id = _resolve_telegram_user_id(user_id)
        if telegram_user_id is None:
            logger.warning("Could not resolve telegram_user_id for user_id=%s", user_id)
            continue

        try:
            http_post_with_retry(
                BOT_NOTIFY_URL,
                {"chat_id": telegram_user_id, "message": notification_text},
            )
            logger.info("Notification sent to user_id=%s", telegram_user_id)
        except Exception as exc:
            logger.error("Failed to notify user %s: %s", telegram_user_id, exc)


def _resolve_telegram_user_id(user_id: int):
    """
    Resolve telegram_user_id from the cached products list.
    We store the telegram_user_id by querying /users endpoint.
    """
    try:
        with httpx.Client(timeout=HTTP_TIMEOUT) as client:
            resp = client.get(f"{API_GATEWAY_URL}/users/{user_id}")
            if resp.status_code == 200:
                return resp.json().get("telegram_user_id")
    except Exception as exc:
        logger.error("Failed to resolve telegram_user_id for user_id=%s: %s", user_id, exc)
    return None


if __name__ == "__main__":
    if CHECK_INTERVAL_SECONDS <= 0:
        logger.info("Scheduler starting in continuous mode (no interval delay)")
    else:
        logger.info(
            "Scheduler starting – check interval: %d second(s)",
            CHECK_INTERVAL_SECONDS,
        )

    logger.info("Running initial product check...")
    check_products()

    while True:
        if CHECK_INTERVAL_SECONDS > 0:
            time.sleep(CHECK_INTERVAL_SECONDS)
        check_products()
