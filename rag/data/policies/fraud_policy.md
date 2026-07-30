# Fraud & Risk Policy

## 1. Seller Risk Assessment
- Sellers with a return rate > 15% over a 30-day period must be flagged for manual review.
- Sellers with > 3 "item not as described" complaints in a week trigger an automatic suspension warning.

## 2. Escalation Confidence Gating
- Support and Risk agents must check model retrieval confidence.
- If the policy context retrieved has low relevance (e.g. edge cases not covered by policy), the agent MUST NOT hallucinate a resolution. 
- Instead, the agent must immediately call `escalate(ticket_id)` to route the issue to a human support agent.
