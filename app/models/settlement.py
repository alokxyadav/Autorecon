from sqlalchemy import Column, Integer, String, Numeric, DateTime
from sqlalchemy.sql import func
from app.database import Base


class SettlementRecord(Base):
    __tablename__ = "settlements"

    id = Column(Integer, primary_key=True, index=True)
    razorpay_settlement_id = Column(String, unique=True, index=True, nullable=False)
    transaction_order_id = Column(String, index=True, nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)   # net amount actually paid out
    fees = Column(Numeric(12, 2), nullable=False, default=0)
    utr = Column(String, index=True, nullable=False)
    settled_at = Column(DateTime(timezone=True), server_default=func.now())
