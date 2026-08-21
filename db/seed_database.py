"""Build the synthetic marketplace SQLite database from db/seed.sql.

    python db/seed_database.py            # create + seed if empty (no-op if already seeded)
    python db/seed_database.py --force    # drop everything and rebuild from seed.sql

Agents also call init_db() lazily on first query, so running this by hand is only needed
when you want a deliberate rebuild — for example after editing seed.sql.
"""

import argparse
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import func, select

from shared.db_models import (
    DB_PATH,
    InventoryItem,
    Order,
    Product,
    Seller,
    SupportTicket,
    get_session,
    init_db,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the synthetic marketplace database")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Drop all tables and rebuild from seed.sql (destroys support tickets created at runtime)",
    )
    args = parser.parse_args()

    init_db(force=args.force)

    session = get_session()
    try:
        print(f"Database: {DB_PATH}")
        for model, label in [
            (Product, "products"),
            (InventoryItem, "inventory rows"),
            (Seller, "sellers"),
            (Order, "orders"),
            (SupportTicket, "support tickets"),
        ]:
            count = session.execute(select(func.count()).select_from(model)).scalar()
            print(f"  {count:>4}  {label}")
    finally:
        session.close()

    print("Seed complete.")


if __name__ == "__main__":
    main()
