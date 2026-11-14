from sqlalchemy import Column, Integer, String, Numeric, DateTime
from sqlalchemy.sql import func
from app.database import Base


class BankStatementLineRecord(Base):
    __tablename__ = "bank_statement_lines"

    id = Column(Integer, primary_key=True, index=True)
    amount = Column(Numeric(12, 2), nullable=False)
    description = Column(String, nullable=False, default="")
    utr_reference = Column(String, index=True, nullable=True)
    value_date = Column(DateTime(timezone=True), server_default=func.now())
