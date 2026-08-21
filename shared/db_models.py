"""Synthetic marketplace store — the SQL half of the PRD architecture.

Every product, seller, order, and ticket the agents report on lives here rather than in
per-agent Python dicts. That mattered for correctness, not just tidiness: the pricing
agent used to key products by slug ("iphone-15") while the inventory agent keyed the same
products by SKU ("iph-15-base"), so `check_stock("iphone-15")` returned "not found" for a
product `get_price` answered happily. One shared products table with both identifiers is
what makes those two agents agree about what exists.

All data is synthetic and generated for this demo — no real marketplace, sellers, or
transactions are involved.
"""

import os
from datetime import date

from sqlalchemy import (
    Date,
    Float,
    ForeignKey,
    Integer,
    String,
    create_engine,
    func,
    select,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

# Reasoning: Path is overridable so a container can point at a mounted volume, but the
# default keeps the database beside the seed file it is built from.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.getenv("MARKETPLACE_DB_PATH", os.path.join(_PROJECT_ROOT, "db", "marketplace.db"))
SEED_SQL_PATH = os.path.join(_PROJECT_ROOT, "db", "seed.sql")


class Base(DeclarativeBase):
    pass


class Product(Base):
    __tablename__ = "products"

    # Reasoning: The human-readable slug is the primary key because it is what users and
    # the LLM actually say ("iphone-15"). The SKU is kept alongside and indexed so
    # warehouse-style lookups by SKU resolve to the same row rather than missing.
    product_id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    sku: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    category: Mapped[str] = mapped_column(String, nullable=False)
    supplier: Mapped[str] = mapped_column(String, nullable=False)
    storage_location: Mapped[str] = mapped_column(String, nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    # Reasoning: Nullable on purpose — not every product has a tracked competitor, and
    # "we don't know" is a materially different answer from "the competitor charges 0".
    competitor_price: Mapped[float | None] = mapped_column(Float, nullable=True)

    inventory: Mapped["InventoryItem"] = relationship(back_populates="product", uselist=False)


class InventoryItem(Base):
    __tablename__ = "inventory"

    product_id: Mapped[str] = mapped_column(ForeignKey("products.product_id"), primary_key=True)
    stock_qty: Mapped[int] = mapped_column(Integer, nullable=False)
    # Reasoning: The warehouse policy defines restock triggers as a percentage of the
    # 30-day moving average, so that average has to be stored, not inferred.
    avg_30d_sales: Mapped[int] = mapped_column(Integer, nullable=False)
    warehouse_zone: Mapped[str] = mapped_column(String, nullable=False)

    product: Mapped[Product] = relationship(back_populates="inventory")


class Seller(Base):
    __tablename__ = "sellers"

    seller_id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    # Reasoning: Field names mirror the thresholds in rag/data/policies/fraud_policy.md
    # (return rate > 15% over 30 days; > 3 complaints in a week) so the stored numbers and
    # the retrieved policy talk about the same quantities.
    return_rate_pct: Mapped[float] = mapped_column(Float, nullable=False)
    complaints_last_week: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="active")
    joined_date: Mapped[date] = mapped_column(Date, nullable=False)


class Order(Base):
    __tablename__ = "orders"

    order_id: Mapped[str] = mapped_column(String, primary_key=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.product_id"), nullable=False)
    seller_id: Mapped[str] = mapped_column(ForeignKey("sellers.seller_id"), nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    order_date: Mapped[date] = mapped_column(Date, nullable=False)


class SupportTicket(Base):
    __tablename__ = "support_tickets"

    ticket_id: Mapped[str] = mapped_column(String, primary_key=True)
    order_id: Mapped[str] = mapped_column(String, nullable=False)
    issue: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="open")
    # Reasoning: Escalations were previously lost with the process, since tickets lived in
    # a module-level dict. Persisting them means `escalate` produces a durable record —
    # the point of a human handoff is that a human can still find it later.
    escalated_reason: Mapped[str | None] = mapped_column(String, nullable=True)


def find_product(session, identifier: str) -> Product | None:
    """Look up a product by slug OR SKU, case-insensitively."""
    # Reasoning: This is the fix for the agents disagreeing about what exists. The LLM
    # says "iphone-15", the warehouse says "IPH-15-BASE", and a user may type either;
    # resolving both to the same row is what stops `get_price` and `check_stock` from
    # giving contradictory answers about the same product.
    if not identifier:
        return None
    key = identifier.strip().lower()
    # Reasoning: Normalise separators before matching. The audit caught the model asking
    # for "premium_tv" while the row is keyed "premium-tv", and the product was reported
    # as non-existent over a single character. Underscores, spaces, and hyphens are all
    # the same word to a user and to an LLM, so they should be the same key here.
    normalized = key.replace("_", "-").replace(" ", "-")
    candidates = {key, normalized}
    for product in session.execute(select(Product)).scalars():
        pid = product.product_id.lower()
        sku = product.sku.lower()
        if pid in candidates or sku in candidates:
            return product
        if pid.replace("-", "") in {c.replace("-", "") for c in candidates}:
            return product
        if sku.replace("-", "") in {c.replace("-", "") for c in candidates}:
            return product
    return None


def find_seller(session, identifier: str) -> "Seller | None":
    """Look up a seller by id or display name, case-insensitively."""
    if not identifier:
        return None
    key = identifier.strip().lower()
    return session.execute(
        select(Seller).where(
            (func.lower(Seller.seller_id) == key) | (func.lower(Seller.name) == key)
        )
    ).scalar_one_or_none()


_engine = None
_SessionFactory = None


def get_engine():
    global _engine
    if _engine is None:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        # Reasoning: check_same_thread=False because the MCP agent pool runs its event
        # loop on a background thread, so sessions are legitimately used off the thread
        # that created the engine.
        _engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
    return _engine


def get_session():
    global _SessionFactory
    if _SessionFactory is None:
        init_db()
        _SessionFactory = sessionmaker(bind=get_engine())
    return _SessionFactory()


def init_db(force: bool = False) -> None:
    """Create the schema and load db/seed.sql if the database is empty."""
    engine = get_engine()

    if force:
        Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    # Reasoning: Seed only when empty, so agent restarts do not duplicate rows or wipe
    # support tickets created during a session. `--force` (via seed_database.py) is the
    # explicit way to rebuild.
    with engine.connect() as conn:
        already_seeded = conn.execute(select(func.count()).select_from(Product.__table__)).scalar()
    if already_seeded:
        return

    if not os.path.exists(SEED_SQL_PATH):
        raise FileNotFoundError(f"Seed file not found: {SEED_SQL_PATH}")

    with open(SEED_SQL_PATH, "r", encoding="utf-8") as f:
        seed_sql = f.read()

    # Reasoning: Schema lives in the models above and data lives in seed.sql, so there is
    # exactly one definition of each. Executed through the raw DBAPI connection because
    # the seed is a multi-statement script, which SQLAlchemy's execute() will not take.
    raw = engine.raw_connection()
    try:
        raw.executescript(seed_sql)
        raw.commit()
    finally:
        raw.close()
