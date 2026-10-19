# scripts/seed.py
# Creates FAKE data (zones, riders, shipments). Same --seed gives exactly the same data every time.
import argparse
import random
from decimal import Decimal

from faker import Faker
from sqlalchemy import delete, func, select, update

from app.db import SessionLocal, settings
from app.models import DeliveryAttempt, ExceptionTask, Rider, Shipment, User, Zone

ZONE_NAMES = ["Dhanmondi", "Gulshan", "Mirpur", "Uttara", "Mohammadpur", "Motijheel"]
RIDERS_PER_ZONE = 3


def seed_database(count: int, seed_value: int) -> None:
    # Safety: this script deletes all rows first, so it must never touch a remote (live) database.
    if settings.db_host not in ("localhost", "127.0.0.1"):
        raise SystemExit("Refusing to run: this script wipes data and only runs on a local database.")

    Faker.seed(seed_value)          # makes Faker's fake names repeatable
    fake = Faker("en_US")
    rng = random.Random(seed_value)  # our own repeatable random number generator

    with SessionLocal() as session:
               # Wipe old data. Children first, then parents, because of the foreign keys.
        session.execute(delete(ExceptionTask))               # points to shipments, so it goes first
        session.execute(update(User).values(rider_id=None))  # keep the users, only unlink them from riders
        session.execute(delete(DeliveryAttempt))
        session.execute(delete(Shipment))
        session.execute(delete(Rider))
        session.execute(delete(Zone))

        zones = [Zone(name=name) for name in ZONE_NAMES]
        session.add_all(zones)
        session.flush()  # sends the zones to the database so they get their ids

        riders = []
        for zone in zones:
            for _ in range(RIDERS_PER_ZONE):
                riders.append(Rider(name=fake.name(), zone_id=zone.id, daily_capacity=rng.randint(15, 25)))
        session.add_all(riders)

        shipments = []
        for i in range(1, count + 1):
            zone = rng.choice(zones)
            is_cod = rng.random() < 0.6  # about 60% are cash on delivery
            shipments.append(
                Shipment(
                    tracking_code=f"DEL{i:06d}",
                    recipient_name=fake.name(),
                    recipient_phone="01" + "".join(rng.choice("0123456789") for _ in range(9)),  # random digits, fake
                    address=f"House {rng.randint(1, 99)}, Road {rng.randint(1, 30)}, {zone.name}",
                    zone_id=zone.id,
                    is_cod=is_cod,
                    cod_amount=Decimal(rng.randint(200, 5000)) if is_cod else Decimal("0.00"),
                )
            )
        session.add_all(shipments)
        session.commit()

        # Print a short summary so we can compare two runs.
        n_zones = session.scalar(select(func.count()).select_from(Zone))
        n_riders = session.scalar(select(func.count()).select_from(Rider))
        n_ship = session.scalar(select(func.count()).select_from(Shipment))
        n_cod = session.scalar(select(func.count()).select_from(Shipment).where(Shipment.is_cod.is_(True)))
        total_cod = session.scalar(select(func.sum(Shipment.cod_amount)))
        first = session.scalar(select(Shipment.recipient_name).order_by(Shipment.id).limit(1))
        print(f"seed={seed_value} zones={n_zones} riders={n_riders} shipments={n_ship} cod={n_cod} total_cod={total_cod} first={first}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed the local database with fake data")
    parser.add_argument("--count", type=int, default=100, help="how many shipments to create")
    parser.add_argument("--seed", type=int, default=42, help="same seed = same data")
    args = parser.parse_args()
    seed_database(args.count, args.seed)
