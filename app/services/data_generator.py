"""
Synthetic data generator.

Produces a realistic-looking batch of transactions, settlements, and bank
statement lines — including deliberately injected discrepancies — so the
matching engine and dashboard have something meaningful to demo without
needing real merchant data.

Uses only the standard library (random, decimal) so it runs with zero extra
dependencies, same as the matching engine.
"""

import random
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.transaction import TransactionRecord
from app.models.settlement import SettlementRecord
from app.models.bank_statement_line import BankStatementLineRecord
from app.services.time_utils import utc_now

FEE_RATE = Decimal("0.02")  # 2% flat, close enough to real payment gateway pricing


def _round2(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"))


def generate_demo_dataset(
    db: Session,
    now: datetime | None = None,
    num_transactions: int = 200,
    seed: int = 42,
) -> dict:
    """Wipes and repopulates the three source tables with a fresh synthetic
    dataset. Returns a summary dict of what was injected, so tests/demos can
    assert against known ground truth.
    """
    random.seed(seed)
    now = now or utc_now()

    db.query(TransactionRecord).delete()
    db.query(SettlementRecord).delete()
    db.query(BankStatementLineRecord).delete()
    db.commit()

    injected = {
        "clean_matches": 0,
        "fee_drift_partials": 0,
        "missing_settlements": 0,
        "duplicate_bank_lines": 0,
        "timing_lag_only": 0,
        "still_pending": 0,
    }

    for i in range(1, num_transactions + 1):
        order_id = f"order_{i:05d}"
        amount = _round2(Decimal(random.randrange(10000, 500000)) / 100)  # ₹100 - ₹5000
        age_days = random.randint(0, 20)
        created_at = now - timedelta(days=age_days, hours=random.randint(0, 23))

        txn = TransactionRecord(
            order_id=order_id,
            amount=amount,
            currency="INR",
            status="captured",
            source="razorpay_test_mode",
            created_at=created_at,
        )
        db.add(txn)
        db.flush()  # get txn.id without committing yet

        fees = _round2(amount * FEE_RATE)
        expected_net = amount - fees
        utr = f"UTR{i:06d}"

        # --- Decide which scenario this transaction represents ---------
        roll = random.random()

        if age_days < 3:
            # Still within the normal settlement cycle — intentionally no
            # settlement row at all. This should classify as PENDING, not
            # a discrepancy, once reconciled.
            injected["still_pending"] += 1
            continue

        if roll < 0.08:
            # ~8%: missing settlement entirely, past the grace period —
            # a genuine discrepancy the engine should flag as UNMATCHED.
            injected["missing_settlements"] += 1
            continue

        if roll < 0.20:
            # ~12%: fee drift beyond tolerance — settlement exists but the
            # net amount is off by more than the fuzzy-match tolerance.
            drift = _round2(Decimal(random.randrange(600, 2000)) / 100)  # ₹6-20 off
            settled_amount = expected_net - drift
            injected["fee_drift_partials"] += 1
        else:
            # Clean match.
            settled_amount = expected_net
            injected["clean_matches"] += 1

        settled_at = created_at + timedelta(days=random.randint(1, 3))
        settlement = SettlementRecord(
            razorpay_settlement_id=f"stl_{i:06d}",
            transaction_order_id=order_id,
            amount=_round2(settled_amount),
            fees=fees,
            utr=utr,
            settled_at=settled_at,
        )
        db.add(settlement)
        db.flush()

        # --- Bank statement line for this settlement --------------------
        # Independently sampled from the match-quality roll above, so a
        # timing lag can happen to a clean match OR a fee-drift case —
        # these are two unrelated real-world failure modes and shouldn't
        # be correlated with each other.
        if random.random() < 0.08:
            injected["timing_lag_only"] += 1
            continue

        bank_line = BankStatementLineRecord(
            amount=_round2(settled_amount),
            description=f"NEFT CR {utr}",
            utr_reference=utr,
            value_date=settled_at + timedelta(hours=random.randint(1, 20)),
        )
        db.add(bank_line)

        if random.random() < 0.03:
            # ~3%: duplicate the bank line to simulate a double-credit /
            # duplicate webhook scenario the engine must catch.
            db.flush()
            dup = BankStatementLineRecord(
                amount=bank_line.amount,
                description=bank_line.description,
                utr_reference=bank_line.utr_reference,
                value_date=bank_line.value_date,
            )
            db.add(dup)
            injected["duplicate_bank_lines"] += 1

    db.commit()
    return injected
