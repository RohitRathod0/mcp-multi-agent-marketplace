import os
import sys

# Reasoning: Add the project root to the path to access the shared RAG + DB modules.
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy import func, select

from rag.retriever import MIN_SIMILARITY, RetrievalResult, retrieve
from shared.db_models import Order, SupportTicket, find_seller, get_session

# Reasoning: Seller records, orders, and tickets all live in the synthetic SQL store.
# Tickets in particular used to be a module-level dict, which meant every escalation was
# lost when the agent process exited — a human handoff nobody could later find is not
# really a handoff.


def _escalation_directive(subject: str, result: RetrievalResult) -> str:
    """The confidence gate required by fraud_policy.md section 2.

    Returns an escalation directive when retrieval confidence is below the grounding
    threshold, or an empty string when the context is trustworthy enough to answer from.
    """
    # Reasoning: This is the difference between a confidence gate and a hopeful sentence
    # in a prompt. rag/data/policies/fraud_policy.md states that risk and support agents
    # "must check model retrieval confidence" and escalate rather than hallucinate; until
    # now nothing in the code measured anything. The number below is the real cosine
    # similarity of the best retrieved policy document, compared against the same
    # calibrated threshold the retriever uses, so the decision is made by measurement
    # rather than by the model's own estimate of how sure it feels.
    if result.is_grounded:
        return ""
    return (
        f"LOW_CONFIDENCE_ESCALATION_REQUIRED: retrieval confidence for {subject} was "
        f"{result.confidence:.2f}, below the grounding threshold of {MIN_SIMILARITY:.2f}. "
        f"Per the fraud policy's escalation gating rule, do NOT answer from general "
        f"knowledge or infer a resolution. Create a support ticket if one does not exist "
        f"and call escalate(ticket_id) to hand this to a human."
    )


def check_seller_risk(seller_id: str) -> str:
    """Assess risk level for a seller based on fraud policies."""
    session = get_session()
    try:
        # Reasoning: Retrieve the risk policy for grounding, and gate on its confidence
        # before reporting any seller numbers at all — quoting metrics alongside an
        # irrelevant policy is how a confident-sounding wrong answer gets produced.
        policy = retrieve(
            "seller risk assessment return rate complaint thresholds", doc_type="policy"
        )
        gate = _escalation_directive(f"seller {seller_id}", policy)
        if gate:
            return gate

        seller = find_seller(session, seller_id)
        if seller is None:
            return f"No risk data found for seller {seller_id}."

        # Reasoning: Format the rate with :g so a whole number renders as "22%" rather
        # than "22.0%". Storing it as a float is right (rates like 18.5% are meaningful),
        # but the extra ".0" changes the factual text agents and evaluators read.
        return (
            f"Seller {seller.name} ({seller.seller_id}) — status: {seller.status}, "
            f"joined {seller.joined_date}. Return rate: {seller.return_rate_pct:g}%, "
            f"complaints in the last week: {seller.complaints_last_week}.\n\n"
            f"[FRAUD POLICY | {policy.confidence_note()}]\n"
            f"{policy.as_context()}"
        )
    finally:
        session.close()


def get_return_pattern(seller_id: str) -> str:
    """Fetch historical flagged return patterns for a seller."""
    session = get_session()
    try:
        seller = find_seller(session, seller_id)
        if seller is None:
            return f"No seller found with id {seller_id}."

        # Reasoning: Pair the seller's actual order history with comparable historical
        # cases, so "unusual pattern" is grounded in this seller's data rather than in
        # the model's impression of the name.
        orders = session.execute(
            select(Order.status, func.count())
            .where(Order.seller_id == seller.seller_id)
            .group_by(Order.status)
        ).all()
        order_summary = (
            ", ".join(f"{status}: {count}" for status, count in orders)
            if orders
            else "no orders on record"
        )

        history = retrieve(
            f"fraud return pattern case similar to {seller.name}", doc_type="historical_case"
        )
        gate = _escalation_directive(f"return patterns for {seller_id}", history)
        if gate:
            return (
                f"Historical return patterns for {seller.name} ({seller.seller_id}) — "
                f"order history: {order_summary}. "
                f"Return rate {seller.return_rate_pct:g}%.\n\n{gate}"
            )

        return (
            f"Historical return patterns for {seller.name} ({seller.seller_id}) — "
            f"order history: {order_summary}. Return rate {seller.return_rate_pct:g}%, "
            f"complaints last week: {seller.complaints_last_week}.\n\n"
            f"[COMPARABLE HISTORICAL CASES | {history.confidence_note()}]\n"
            f"{history.as_context()}"
        )
    finally:
        session.close()


def create_support_ticket(order_id: str, issue: str) -> str:
    """Create a support ticket for a user issue."""
    session = get_session()
    try:
        # Reasoning: Sequence from what is already stored so ticket ids stay unique across
        # restarts. The previous in-memory counter restarted at 1 every process launch and
        # would happily hand out an id that already belonged to another ticket.
        existing = session.execute(select(func.count()).select_from(SupportTicket)).scalar() or 0
        ticket_id = f"TICK-{existing + 1:04d}"

        order = session.execute(
            select(Order).where(func.lower(Order.order_id) == order_id.strip().lower())
        ).scalar_one_or_none()

        ticket = SupportTicket(ticket_id=ticket_id, order_id=order_id, issue=issue, status="open")
        session.add(ticket)
        session.commit()

        # Reasoning: Say plainly when the order is unknown rather than failing. A customer
        # quoting a wrong order number is an ordinary support case, and the ticket is still
        # the right artefact — but a human should see that the id did not resolve.
        order_note = (
            f" Order {order.order_id} is currently '{order.status}' (placed {order.order_date})."
            if order
            else f" Note: order {order_id} was not found in the marketplace records."
        )
        return f"Created support ticket {ticket_id} for order {order_id}.{order_note}"
    finally:
        session.close()


def escalate(ticket_id: str, reason: str = "") -> str:
    """Escalate a ticket to a human when confidence is low."""
    session = get_session()
    try:
        ticket = session.execute(
            select(SupportTicket).where(
                func.lower(SupportTicket.ticket_id) == ticket_id.strip().lower()
            )
        ).scalar_one_or_none()

        if ticket is None:
            return f"Failed to escalate. Ticket {ticket_id} not found."

        ticket.status = "escalated_to_human"
        # Reasoning: Persist WHY it escalated, not just that it did. A human picking this
        # up needs to know whether the agent hit a policy edge case or simply could not
        # find grounding, and that reason is exactly what the confidence gate produced.
        ticket.escalated_reason = reason or "Low confidence / policy edge case."
        session.commit()

        return (
            f"Ticket {ticket_id} successfully escalated to a human agent "
            f"(reason: {ticket.escalated_reason}). Please inform the user."
        )
    finally:
        session.close()
