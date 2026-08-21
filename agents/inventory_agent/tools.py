import os
import sys

# Reasoning: Add the project root to the path to access the shared RAG + DB modules.
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy import select

from rag.retriever import retrieve
from shared.db_models import InventoryItem, Product, find_product, get_session

# Reasoning: Stock levels come from the shared SQL store rather than a dict keyed by SKU.
# The old dict keyed products as "iph-15-base" while the pricing agent keyed the same
# product as "iphone-15", so the two agents disagreed about which products existed.
# find_product() resolves either identifier to the same row.


def check_stock(product_id: str) -> str:
    """Check if an item is in stock."""
    session = get_session()
    try:
        product = find_product(session, product_id)
        if product is None or product.inventory is None:
            return f"Product {product_id} not found in inventory."
        item = product.inventory
        return (
            f"{product.name} ({product.product_id}, SKU {product.sku}) has "
            f"{item.stock_qty} units in stock in the {item.warehouse_zone}."
        )
    finally:
        session.close()


def forecast_restock(product_id: str) -> str:
    """Forecast if a restock is needed based on warehouse policy."""
    session = get_session()
    try:
        product = find_product(session, product_id)
        if product is None or product.inventory is None:
            return f"Product {product_id} not found for forecasting."

        # Reasoning: Ground the restock decision in the warehouse policy.
        policy = retrieve("restock forecasting rules and lead time", doc_type="policy")
        if not policy.is_grounded:
            return (
                f"INSUFFICIENT_GROUNDING: no warehouse policy matched this request "
                f"(best similarity {policy.confidence:.2f}). Do not guess a restock "
                f"threshold — escalate to a human."
            )

        item = product.inventory
        # Reasoning: Compute the policy's trigger point (20% of the 30-day moving average)
        # here rather than asking the model to do arithmetic on it. The policy text still
        # goes along so the model can explain and cite the rule it is applying.
        trigger_point = item.avg_30d_sales * 0.2
        return (
            f"Current stock for {product.name} ({product.product_id}) is {item.stock_qty} "
            f"units. 30-day average sales volume is {item.avg_30d_sales}, so the policy "
            f"restock trigger (20% of that average) is {trigger_point:.1f} units. "
            f"Supplier is {product.supplier}.\n\n"
            f"[WAREHOUSE POLICY | {policy.confidence_note()}]\n"
            f"{policy.as_context()}"
        )
    finally:
        session.close()


def flag_low_stock() -> str:
    """Scan all inventory and flag low stock items according to policy."""
    session = get_session()
    try:
        policy = retrieve("low stock flagging rules threshold", doc_type="policy")
        if not policy.is_grounded:
            return (
                f"INSUFFICIENT_GROUNDING: no warehouse policy matched this request "
                f"(best similarity {policy.confidence:.2f}). Do not invent a low-stock "
                f"threshold — escalate to a human."
            )

        rows = session.execute(
            select(Product, InventoryItem)
            .join(InventoryItem, Product.product_id == InventoryItem.product_id)
            .order_by(InventoryItem.stock_qty)
        ).all()

        inventory_summary = "\n".join(
            f"- {p.name} ({p.product_id}, SKU {p.sku}): {inv.stock_qty} units, "
            f"30-day avg sales {inv.avg_30d_sales}, zone {inv.warehouse_zone}"
            for p, inv in rows
        )

        return (
            f"Please review the following inventory and flag items based on the policy:\n\n"
            f"[CURRENT INVENTORY]\n{inventory_summary}\n\n"
            f"[WAREHOUSE POLICY | {policy.confidence_note()}]\n"
            f"{policy.as_context()}"
        )
    finally:
        session.close()
