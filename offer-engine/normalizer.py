import hashlib
import json
import logging
import re

logger = logging.getLogger(__name__)


def strip_currency(value) -> int:
    """Remove ₹, commas, whitespace from a value and convert to int."""
    if value is None:
        return 0
    text = str(value)
    cleaned = re.sub(r"[₹,\s]", "", text)
    cleaned = re.sub(r"[^\d]", "", cleaned)
    return int(cleaned) if cleaned else 0


def normalize_offers(offers: list) -> list:
    """Normalize and sort offers deterministically."""
    normalized = []
    for offer in offers:
        normalized.append(
            {
                "bank_name": str(offer.get("bank_name", "")).strip().upper(),
                "card_type": str(offer.get("card_type", "")).strip().capitalize() if offer.get("card_type") else None,
                "discount_value": strip_currency(offer.get("discount_value")),
                "min_transaction_amount": strip_currency(offer.get("min_transaction", offer.get("min_transaction_amount"))),
            }
        )
    # Sort deterministically
    normalized.sort(key=lambda x: (x["bank_name"], x["card_type"] or ""))
    return normalized


def compute_hash(normalized_offers: list) -> str:
    """Compute a SHA-256 hash of the sorted, serialized offers list."""
    serialized = json.dumps(normalized_offers, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
