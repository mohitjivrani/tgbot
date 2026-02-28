from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime

from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_user_id = Column(String, unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    products = relationship("Product", back_populates="user", cascade="all, delete-orphan")


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    product_url = Column(Text, nullable=False)
    platform = Column(String, nullable=False)
    product_name = Column(String, nullable=True)
    preferred_pincode = Column(String(10), nullable=True)
    last_price = Column(Integer, nullable=True)
    last_availability = Column(Boolean, nullable=True)
    last_deliverable = Column(Boolean, nullable=True)
    last_available_at = Column(DateTime, nullable=True)
    last_available_price = Column(Integer, nullable=True)
    last_offer_hash = Column(String, nullable=True)
    last_checked_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="products")
    bank_offers = relationship("BankOffer", back_populates="product", cascade="all, delete-orphan")


class BankOffer(Base):
    __tablename__ = "bank_offers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    bank_name = Column(String, nullable=False)
    card_type = Column(String, nullable=True)
    discount_value = Column(Integer, nullable=True)
    min_transaction_amount = Column(Integer, nullable=True)
    offer_hash = Column(String, nullable=False)

    product = relationship("Product", back_populates="bank_offers")
