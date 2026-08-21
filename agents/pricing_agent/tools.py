import os
import sys

# Reasoning: Add the project root to the path so we can import the shared 'rag' and
# 'shared' modules.
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from rag.retriever import retrieve
from shared.db_models import find_product, get_session

# Reasoning: Product and competitor prices now come from the synthetic SQL store
# (db/seed.sql) instead of module-level dicts. Two agents keying the same products
# differently — slug here, SKU in inventory — is what made `get_price("iphone-15")`
# succeed while `check_stock("iphone-15")` reported the product did not exist.


def get_price(product_id: str) -> str:
    """Retrieves the current baseline price for a product."""
    session = get_session()
    try:
        product = find_product(session, product_id)
        if product is None:
            return f"Product {product_id} not found in catalog."
        return (
            f"The current price for {product.name} ({product.product_id}, "
            f"SKU {product.sku}) is ${product.price:.2f}."
        )
    finally:
        session.close()


def suggest_discount(product_id: str, context: str) -> str:
    """Suggests a discount strategy by grounding the decision in pricing policies."""
    session = get_session()
    try:
        product = find_product(session, product_id)
        if product is None:
            return f"Product {product_id} not found in catalog."

        # Reasoning: Retrieve pricing policies and historical outcomes to ground the
        # suggestion. Both arms are checked for grounding before being used.
        policy = retrieve(f"discount rules for {context}", doc_type="policy")
        history = retrieve(
            f"historical discount outcome for {product.name}", doc_type="historical_case"
        )

        # Reasoning: Refuse rather than improvise. If no pricing policy cleared the
        # similarity threshold there is nothing to base a discount on, and inventing one
        # is precisely the hallucination this component exists to prevent.
        if not policy.is_grounded:
            return (
                f"INSUFFICIENT_GROUNDING: no pricing policy in the knowledge base matched "
                f"this request (best similarity {policy.confidence:.2f}). Do not invent a "
                f"discount — escalate to a human pricing manager."
            )

        stock_note = ""
        if product.inventory is not None:
            # Reasoning: Warehouse policy pauses discounting on low-stock items, so the
            # pricing agent needs the stock level to apply that rule rather than
            # recommending a markdown the warehouse policy forbids.
            stock_note = (
                f"\n\n[CURRENT STOCK] {product.inventory.stock_qty} units "
                f"(30-day average sales: {product.inventory.avg_30d_sales})."
            )

        return (
            f"Discount analysis for {product.name} ({product.product_id}) at "
            f"${product.price:.2f}.{stock_note}\n\n"
            f"[PRICING POLICY | {policy.confidence_note()}]\n"
            f"{policy.as_context()}\n\n"
            f"[HISTORICAL CASES]\n{history.as_context()}"
        )
    finally:
        session.close()


def compare_competitor_price(product_id: str) -> str:
    """Compares our price against known competitor prices."""
    session = get_session()
    try:
        product = find_product(session, product_id)
        if product is None:
            return f"Product {product_id} not found in catalog."

        # Reasoning: A missing competitor price is stored as NULL and reported as unknown.
        # Treating it as 0 (or silently omitting it) would let the model conclude we are
        # wildly overpriced against a competitor that was simply never tracked.
        if product.competitor_price is None:
            return (
                f"Our price for {product.name} is ${product.price:.2f}. "
                f"Competitor price data not available for this product."
            )

        delta = product.price - product.competitor_price
        position = "higher than" if delta > 0 else "lower than" if delta < 0 else "level with"
        return (
            f"Our price for {product.name} is ${product.price:.2f}; the tracked competitor "
            f"price is ${product.competitor_price:.2f}. We are ${abs(delta):.2f} "
            f"({abs(delta) / product.competitor_price * 100:.1f}%) {position} the competitor."
        )
    finally:
        session.close()
