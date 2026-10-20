# tests/test_known_answers.py
# Known-answer test: Python computes the expected totals while generating fake data,
# then we check that PostgreSQL (SQL) and pandas both give exactly the same answers.
import random
import uuid
from decimal import Decimal

import pandas as pd
import pytest
from sqlalchemy import func, select

from app.models import Shipment, Zone


@pytest.mark.parametrize("count", [100, 10000])  # run the same test at two sizes
def test_totals_match_known_answer(db, count):
    # A zone with a unique name, so rows already in the dev database never mix with ours
    zone = Zone(name=f"TestZone_{uuid.uuid4().hex[:8]}")
    db.add(zone)
    db.flush()

    rng = random.Random(123)  # fixed seed: same data every run
    expected_total = 0
    expected_cod_count = 0
    expected_cod_sum = Decimal("0.00")

    shipments = []
    for i in range(count):
        is_cod = rng.random() < 0.6
        amount = Decimal(rng.randint(200, 5000)) if is_cod else Decimal("0.00")
        # The KNOWN ANSWER is counted here, in plain Python, while we generate the data
        expected_total += 1
        if is_cod:
            expected_cod_count += 1
            expected_cod_sum += amount
        shipments.append(
            Shipment(
                tracking_code=f"KA{zone.id}-{i:05d}",
                recipient_name="Test Person",
                recipient_phone="01700000000",
                address="House 1, Road 1, Test Zone",
                zone_id=zone.id,
                is_cod=is_cod,
                cod_amount=amount,
            )
        )
    db.add_all(shipments)
    db.flush()  # send rows to the database (still inside the test transaction)

    # Calculation 1: SQL, inside PostgreSQL
    sql_total = db.scalar(select(func.count()).select_from(Shipment).where(Shipment.zone_id == zone.id))
    sql_cod_count = db.scalar(
        select(func.count()).select_from(Shipment).where(Shipment.zone_id == zone.id, Shipment.is_cod.is_(True))
    )
    sql_cod_sum = db.scalar(
        select(func.sum(Shipment.cod_amount)).where(Shipment.zone_id == zone.id, Shipment.is_cod.is_(True))
    )

    # Calculation 2: pandas, in Python memory (same connection, so it sees our uncommitted rows)
    df = pd.read_sql(select(Shipment).where(Shipment.zone_id == zone.id), db.connection())
    pandas_total = len(df)
    pandas_cod_count = int(df["is_cod"].sum())
    pandas_cod_sum = Decimal(str(df.loc[df["is_cod"], "cod_amount"].sum()))

    # All three must agree with the known answer
    assert sql_total == pandas_total == expected_total
    assert sql_cod_count == pandas_cod_count == expected_cod_count
    assert sql_cod_sum == pandas_cod_sum == expected_cod_sum