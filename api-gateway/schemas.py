from pydantic import BaseModel, HttpUrl
from typing import Optional, List
from datetime import datetime


class TrackRequest(BaseModel):
    url: str
    telegram_user_id: str
    pincode: Optional[str] = None


class BankOfferSchema(BaseModel):
    bank_name: str
    card_type: Optional[str] = None
    discount_value: Optional[int] = None
    min_transaction_amount: Optional[int] = None
    offer_hash: str

    class Config:
        from_attributes = True


class ProductResponse(BaseModel):
    id: int
    user_id: int
    product_url: str
    platform: str
    product_name: Optional[str] = None
    preferred_pincode: Optional[str] = None
    last_price: Optional[int] = None
    last_availability: Optional[bool] = None
    last_deliverable: Optional[bool] = None
    last_available_at: Optional[datetime] = None
    last_available_price: Optional[int] = None
    last_offer_hash: Optional[str] = None
    last_checked_at: Optional[datetime] = None
    bank_offers: List[BankOfferSchema] = []

    class Config:
        from_attributes = True


class ProductUpdate(BaseModel):
    product_name: Optional[str] = None
    preferred_pincode: Optional[str] = None
    last_price: Optional[int] = None
    last_availability: Optional[bool] = None
    last_deliverable: Optional[bool] = None
    last_available_at: Optional[datetime] = None
    last_available_price: Optional[int] = None
    last_offer_hash: Optional[str] = None
    bank_offers: Optional[List[dict]] = None


class UserCreate(BaseModel):
    telegram_user_id: str


class UserResponse(BaseModel):
    id: int
    telegram_user_id: str
    created_at: datetime

    class Config:
        from_attributes = True
