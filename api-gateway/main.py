import os
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional, List

from fastapi import FastAPI, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from dotenv import load_dotenv
from urllib.parse import urlparse, urlunparse

from database import engine, get_db, Base
from models import User, Product, BankOffer
from schemas import (
    TrackRequest,
    ProductResponse,
    ProductUpdate,
    UserCreate,
    UserResponse,
    BankOfferSchema,
)

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Creating database tables if they do not exist...")
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE products ADD COLUMN IF NOT EXISTS preferred_pincode VARCHAR(10)"))
        conn.execute(text("ALTER TABLE products ADD COLUMN IF NOT EXISTS last_deliverable BOOLEAN"))
        conn.execute(text("ALTER TABLE products ADD COLUMN IF NOT EXISTS last_available_at TIMESTAMP"))
        conn.execute(text("ALTER TABLE products ADD COLUMN IF NOT EXISTS last_available_price INTEGER"))
    logger.info("Database tables ready.")
    yield


app = FastAPI(title="API Gateway", version="1.0.0", lifespan=lifespan)


def detect_platform(url: str) -> Optional[str]:
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        host = parsed.netloc.lower()
        # Strip port if present (e.g., "flipkart.com:443" → "flipkart.com")
        host = host.split(":")[0]
        if host == "flipkart.com" or host.endswith(".flipkart.com") or host == "fkrt.it":
            return "flipkart"
        if host == "shop.vivo.com" or host.endswith(".shop.vivo.com"):
            return "vivo"
    except Exception:
        pass
    return None


def normalize_product_url(url: str) -> str:
    parsed = urlparse(url.strip())
    normalized_path = parsed.path.rstrip("/") or "/"
    return urlunparse(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            normalized_path,
            "",
            "",
            "",
        )
    )


def normalize_pincode(pincode: Optional[str]) -> Optional[str]:
    if pincode is None:
        return None
    cleaned = "".join(ch for ch in str(pincode).strip() if ch.isdigit())
    if cleaned == "":
        return None
    if len(cleaned) != 6:
        raise HTTPException(status_code=400, detail="Pincode must be a 6-digit number")
    return cleaned


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/users", response_model=UserResponse)
def create_or_get_user(payload: UserCreate, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.telegram_user_id == payload.telegram_user_id).first()
    if not user:
        user = User(telegram_user_id=payload.telegram_user_id)
        db.add(user)
        db.commit()
        db.refresh(user)
        logger.info("Created new user: %s", payload.telegram_user_id)
    return user


@app.get("/users/{user_db_id}", response_model=UserResponse)
def get_user_by_db_id(user_db_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_db_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@app.post("/track", response_model=ProductResponse, status_code=201)
def track_product(payload: TrackRequest, db: Session = Depends(get_db)):
    normalized_url = normalize_product_url(payload.url)
    normalized_pincode = normalize_pincode(payload.pincode)
    platform = detect_platform(normalized_url)
    if platform is None:
        raise HTTPException(
            status_code=400,
            detail="Unsupported URL. Only flipkart.com, fkrt.it, and shop.vivo.com/in are supported.",
        )

    # Get or create user
    user = db.query(User).filter(User.telegram_user_id == payload.telegram_user_id).first()
    if not user:
        user = User(telegram_user_id=payload.telegram_user_id)
        db.add(user)
        db.flush()
        logger.info("Auto-created user: %s", payload.telegram_user_id)

    # Check for duplicate tracking
    existing = (
        db.query(Product)
        .filter(Product.user_id == user.id, Product.product_url == normalized_url)
        .first()
    )
    if existing:
        if existing.preferred_pincode != normalized_pincode:
            existing.preferred_pincode = normalized_pincode
            db.commit()
            db.refresh(existing)
        logger.info("Product already tracked: %s", normalized_url)
        return existing

    product = Product(
        user_id=user.id,
        product_url=normalized_url,
        platform=platform,
        preferred_pincode=normalized_pincode,
    )
    db.add(product)
    db.commit()
    db.refresh(product)
    logger.info("Started tracking product id=%d url=%s platform=%s", product.id, payload.url, platform)
    return product


@app.get("/products", response_model=List[ProductResponse])
def list_products(user_id: Optional[str] = Query(None), db: Session = Depends(get_db)):
    query = db.query(Product)
    if user_id:
        user = db.query(User).filter(User.telegram_user_id == user_id).first()
        if not user:
            return []
        query = query.filter(Product.user_id == user.id)
    products = query.all()
    return products


@app.delete("/products/{product_id}", status_code=204)
def delete_product(product_id: int, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    db.delete(product)
    db.commit()
    logger.info("Deleted product id=%d", product_id)


@app.patch("/products/{product_id}", response_model=ProductResponse)
def update_product(product_id: int, payload: ProductUpdate, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    if payload.product_name is not None:
        product.product_name = payload.product_name
    if payload.preferred_pincode is not None:
        product.preferred_pincode = normalize_pincode(payload.preferred_pincode)
    if payload.last_price is not None:
        product.last_price = payload.last_price
    if payload.last_availability is not None:
        product.last_availability = payload.last_availability
    if payload.last_deliverable is not None:
        product.last_deliverable = payload.last_deliverable
    if payload.last_available_at is not None:
        product.last_available_at = payload.last_available_at
    if payload.last_available_price is not None:
        product.last_available_price = payload.last_available_price
    if payload.last_offer_hash is not None:
        product.last_offer_hash = payload.last_offer_hash

    product.last_checked_at = datetime.utcnow()

    # Replace bank offers if provided
    if payload.bank_offers is not None:
        for offer in product.bank_offers:
            db.delete(offer)
        db.flush()
        for offer_data in payload.bank_offers:
            bank_offer = BankOffer(
                product_id=product.id,
                bank_name=offer_data.get("bank_name", ""),
                card_type=offer_data.get("card_type"),
                discount_value=offer_data.get("discount_value"),
                min_transaction_amount=offer_data.get("min_transaction_amount"),
                offer_hash=offer_data.get("offer_hash", ""),
            )
            db.add(bank_offer)

    db.commit()
    db.refresh(product)
    logger.info("Updated product id=%d", product_id)
    return product
