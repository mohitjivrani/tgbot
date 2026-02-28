import os
import logging
from datetime import datetime
from typing import Optional, List

from fastapi import FastAPI, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from dotenv import load_dotenv

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

app = FastAPI(title="API Gateway", version="1.0.0")


@app.on_event("startup")
def startup():
    logger.info("Creating database tables if they do not exist...")
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables ready.")


def detect_platform(url: str) -> Optional[str]:
    if "flipkart.com" in url or "fkrt.it" in url:
        return "flipkart"
    if "shop.vivo.com" in url:
        return "vivo"
    return None


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
    platform = detect_platform(payload.url)
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
        .filter(Product.user_id == user.id, Product.product_url == payload.url)
        .first()
    )
    if existing:
        logger.info("Product already tracked: %s", payload.url)
        return existing

    product = Product(
        user_id=user.id,
        product_url=payload.url,
        platform=platform,
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
    if payload.last_price is not None:
        product.last_price = payload.last_price
    if payload.last_availability is not None:
        product.last_availability = payload.last_availability
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
