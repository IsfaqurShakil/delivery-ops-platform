# scripts/verify_counts.py
# Independent check: compute totals with pandas and compare with totals computed by PostgreSQL (SQL).
# Two different engines, same data. If they disagree, something is wrong.
from decimal import Decimal

import pandas as pd
from sqlalchemy import func, select

from app.db import SessionLocal, engine
from app.models import Shipment


def main() -> None:
    # 1) Read the whole shipments table into a pandas DataFrame
    df = pd.read_sql(select(Shipment), engine)

    # 2) pandas calculation (done in Python memory)
    pandas_total = len(df)
    pandas_cod_count = int(df["is_cod"].sum())
    pandas_cod_sum = df.loc[df["is_cod"], "cod_amount"].sum()

    # 3) SQL calculation (done inside PostgreSQL)
    with SessionLocal() as session:
        sql_total = session.scalar(select(func.count()).select_from(Shipment))
        sql_cod_count = session.scalar(
            select(func.count()).select_from(Shipment).where(Shipment.is_cod.is_(True))
        )
        sql_cod_sum = session.scalar(select(func.sum(Shipment.cod_amount)).where(Shipment.is_cod.is_(True)))

    # 4) Compare (pandas amount converted back to Decimal; Decimal("15566946.0") == Decimal("15566946.00") is True)
    checks = {
        "total shipments": (pandas_total, sql_total),
        "cod shipments": (pandas_cod_count, sql_cod_count),
       "total cod amount": (Decimal(str(pandas_cod_sum)), sql_cod_sum),
    }
    all_ok = True
    for name, (p, s) in checks.items():
        ok = p == s
        all_ok = all_ok and ok
        print(f"{'PASS' if ok else 'FAIL'}  {name}: pandas={p} sql={s}")

    print("ALL CHECKS PASSED" if all_ok else "SOME CHECKS FAILED")


if __name__ == "__main__":
    main()