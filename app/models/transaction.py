from sqlalchemy import Column, Integer, String, Numeric, DateTime
from sqlalchemy.sql import func
from app.database import Base


class TransactionRecord(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(String, unique=True, index=True, nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)
    currency = Column(String(3), nullable=False, default="INR")
    status = Column(String, nullable=False, default="captured")  # captured|failed|refunded
    source = Column(String, nullable=False, default="razorpay_test_mode")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
