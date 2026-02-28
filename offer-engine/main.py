import logging
from typing import List, Optional

from fastapi import FastAPI
from pydantic import BaseModel
from dotenv import load_dotenv

from normalizer import normalize_offers, compute_hash

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Offer Engine", version="1.0.0")


class OfferItem(BaseModel):
    bank_name: str
    card_type: Optional[str] = None
    discount_value: Optional[object] = None
    min_transaction: Optional[object] = None
    min_transaction_amount: Optional[object] = None


class AnalyzeRequest(BaseModel):
    offers: List[OfferItem] = []
    previous_hash: Optional[str] = None


class AnalyzeResponse(BaseModel):
    changed: bool
    change_type: Optional[str]
    new_hash: str
    normalized_offers: list


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/analyze", response_model=AnalyzeResponse)
def analyze(payload: AnalyzeRequest):
    raw_offers = [o.model_dump() for o in payload.offers]
    normalized = normalize_offers(raw_offers)
    new_hash = compute_hash(normalized)

    changed = new_hash != payload.previous_hash

    if changed:
        if payload.previous_hash is None:
            change_type = "INITIAL_FETCH"
        else:
            change_type = "BANK_OFFER_UPDATED"
    else:
        change_type = None

    logger.info(
        "Analyze: changed=%s change_type=%s new_hash=%s",
        changed,
        change_type,
        new_hash,
    )

    return AnalyzeResponse(
        changed=changed,
        change_type=change_type,
        new_hash=new_hash,
        normalized_offers=normalized,
    )
