# PRD — Multi-Agent MCP Marketplace Orchestrator

**Author:** Rohit Rathod
**Status:** Draft v1
**Target:** Resume/portfolio project — AI product-company signal (agentic systems, MCP, RAG, prompt engineering)

---

## 1. One-liner

A simulated e-commerce/marketplace backend where independent, specialized agents (pricing, inventory, risk, support) each run behind their own MCP server, and a central orchestrator agent routes user/business requests to the right agent(s), combining results via a shared RAG knowledge base — mirroring how real AI product companies compose multi-service agentic systems in production.

---

## 2. Problem Statement

Most portfolio "AI agent" projects are single-agent, single-tool RAG chatbots. They don't demonstrate the harder, more production-relevant problem: **coordinating multiple independent agents/services, each with their own tools and context, through a well-defined protocol (MCP), with reliable routing and shared grounding.**

This project exists to close that gap — to produce a system whose architecture looks like what an AI product company (fintech, SaaS, marketplace) would actually deploy internally, not a demo notebook.

---

## 3. Goals

- Demonstrate **MCP server design**: multiple independent MCP servers, each exposing a clean, minimal tool surface.
- Demonstrate **agent orchestration**: a router/orchestrator agent that decides which sub-agent(s) to call, in what order, and how to merge their outputs.
- Demonstrate **RAG as shared context**: a common knowledge base (product catalog, policies, historical transactions) that multiple agents query, ensuring consistent grounding across agents.
- Demonstrate **prompt engineering as a measurable discipline**: versioned prompts, few-shot examples, and an eval harness showing accuracy/routing-correctness improvement over iterations.
- Produce clear, quotable resume bullets and a demoable repo with a working README + architecture diagram.

### Non-Goals
- Not building a real payment/transaction system — all data is simulated/synthetic.
- Not optimizing for scale/production traffic — this is a correctness- and architecture-focused demo, not a load-tested service.
- Not building a custom UI framework — a simple chat/dashboard UI is enough to demo the flow.

---

## 4. Use Case / Scenario

Simulated marketplace (e.g. an electronics marketplace). A user or internal ops person asks natural-language questions or gives commands such as:

- "Is the iPhone 15 in stock, and is this a good time to discount it?"
- "Flag any suspicious sellers with unusual return patterns this month."
- "A customer says their order never arrived — what should I do?"

The orchestrator parses intent, decides which specialized agent(s) are relevant, calls their MCP tools, retrieves grounding context via RAG where needed, and returns a single coherent, cited answer/action.

---

## 5. System Architecture

```
                        ┌─────────────────────┐
                        │   User / Ops Client   │
                        └──────────┬───────────┘
                                   │ natural language request
                                   ▼
                        ┌─────────────────────┐
                        │  Orchestrator Agent   │
                        │  (intent + routing)   │
                        └──────────┬───────────┘
              ┌────────────────────┼────────────────────┐
              ▼                    ▼                     ▼
     ┌────────────────┐  ┌──────────────────┐  ┌────────────────────┐
     │ Pricing Agent   │  │ Inventory Agent   │  │ Risk/Support Agent │
     │ (MCP server)    │  │ (MCP server)      │  │ (MCP server)       │
     └───────┬─────────┘  └────────┬──────────┘  └──────────┬─────────┘
             │                      │                        │
             └──────────────┬───────┴────────────┬───────────┘
                             ▼                    ▼
                   ┌──────────────────┐  ┌──────────────────────┐
                   │  Shared RAG Store  │  │  Synthetic DB (SQL)   │
                   │  (Qdrant/Chroma)   │  │  orders/sellers/txns  │
                   └──────────────────┘  └──────────────────────┘
```

Each agent is a **separate process** exposing an MCP server over its own tool surface — not just a function call inside a monolith. The orchestrator talks to each over the MCP protocol, the same way Claude Desktop or any MCP client would.

---

## 6. Agents & Tool Surfaces

### 6.1 Orchestrator Agent
- Not a domain agent — purely routes and composes.
- Tools it calls (as an MCP *client*): all tools below.
- Responsibilities: intent classification, multi-agent call planning, response synthesis, citation merging, conflict resolution (e.g. pricing says "discount" but risk flags the seller).

### 6.2 Pricing Agent (MCP server)
- Tools: `get_price(product_id)`, `suggest_discount(product_id, context)`, `compare_competitor_price(product_id)`
- RAG use: pulls pricing policy docs + historical price-elasticity notes for grounding.

### 6.3 Inventory Agent (MCP server)
- Tools: `check_stock(product_id)`, `forecast_restock(product_id)`, `flag_low_stock()`
- RAG use: product catalog + warehouse policy docs.

### 6.4 Risk/Support Agent (MCP server)
- Tools: `check_seller_risk(seller_id)`, `get_return_pattern(seller_id)`, `create_support_ticket(order_id, issue)`, `escalate(ticket_id)`
- RAG use: fraud/return policy docs + historical flagged-seller cases.
- Includes a **confidence-gated escalation rule**: if retrieval/model confidence is low, escalate to a human instead of answering — a deliberate reliability feature worth calling out in interviews.

---

## 7. RAG Design

- **Store:** Qdrant or ChromaDB, one shared collection namespaced by document type (`policy`, `catalog`, `historical_case`).
- **Ingestion:** synthetic policy docs, product catalog entries, and historical case logs (all generated/curated by you, clearly labeled as synthetic data).
- **Retrieval:** hybrid (BM25 + embeddings), top-k with a minimum similarity threshold; if threshold not met, agent returns "insufficient grounding" rather than hallucinating.
- **Why shared, not per-agent:** forces you to solve namespace/access-control design (pricing agent shouldn't retrieve risk-only docs) — another concrete design decision to discuss in interviews.

---

## 8. Prompt Engineering Strategy

- Maintain a `/prompts` directory with **versioned system prompts** per agent (`pricing_v1.md`, `pricing_v2.md`, …).
- Build a small **eval set** (30–50 hand-written queries with expected routing + expected tool calls).
- Track per-version metrics:
  - Routing accuracy (did the orchestrator call the right agent?)
  - Tool-call correctness (right tool, right arguments)
  - Faithfulness (did the answer stay grounded in retrieved context, no hallucinated facts?)
- Log results in a simple `eval_results.csv` / small dashboard — this becomes the concrete "improved X% → Y%" resume metric instead of a vague claim.

---

## 9. Tech Stack (proposed)

| Layer | Choice |
|---|---|
| Agent orchestration | LangGraph (or custom router) |
| MCP servers | Python `mcp` SDK, one process per agent |
| LLM | Claude API (tool use) |
| Vector store | Qdrant or ChromaDB |
| Structured DB | SQLite/Postgres for synthetic orders/sellers |
| Backend/API | FastAPI |
| Frontend | Minimal React/TSX chat + agent-trace viewer (shows which agents were called, in what order) |
| Eval harness | Custom Python script + CSV/JSON results |
| Deployment | Docker Compose (each MCP server as its own container) |

---

## 10. Milestones

| Phase | Deliverable |
|---|---|
| 1 | Single MCP server (Pricing Agent) working end-to-end with RAG + 3 tools |
| 2 | Add Inventory + Risk agents as separate MCP servers |
| 3 | Build orchestrator with routing + multi-agent composition |
| 4 | Build eval harness, run prompt v1 → v2 → v3, record metrics |
| 5 | Frontend trace viewer + polish + README + architecture diagram |
| 6 | Deploy via Docker Compose, record demo video/gif for README |

---

## 11. Success Metrics

- Orchestrator routing accuracy ≥ 90% on eval set.
- Zero hallucinated facts in a manual 20-query audit (all claims traceable to retrieved context).
- All 3 agents independently runnable/testable as standalone MCP servers (proves modularity).
- End-to-end multi-agent query (touching 2+ agents) resolves correctly and cites sources.

---

## 12. Draft Resume Bullets (fill in real numbers once measured)

- Designed and built a multi-agent marketplace system with 3 independent MCP servers (pricing, inventory, risk/support), each exposing isolated tool surfaces, coordinated by a custom orchestrator agent.
- Implemented a shared RAG layer (Qdrant/ChromaDB) with namespaced retrieval and confidence-gated escalation to prevent hallucinated responses under low-grounding conditions.
- Built a prompt-versioning eval harness across 3 prompt iterations, improving orchestrator routing accuracy from X% to Y% and tool-call correctness from A% to B%.
- Containerized the full multi-agent system with Docker Compose, with each MCP server independently deployable and testable.

---

## 13. Open Questions

- Exact domain flavor: keep it generic e-commerce, or lean fintech (pricing → interest-rate agent, risk → credit-risk agent) to align tighter with INVEX/Credit Risk Scorecard story? (worth deciding before Phase 1)
- Real synthetic dataset source vs. LLM-generated synthetic data for catalog/orders — LLM-generated is faster but needs a sanity/realism pass.
