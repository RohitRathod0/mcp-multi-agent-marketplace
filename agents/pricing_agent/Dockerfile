# Pricing Agent — standalone MCP server image.
# Build from the PROJECT ROOT, not this directory, because the image needs the shared
# rag/ layer as well as this agent:
#   docker build -f agents/pricing_agent/Dockerfile -t mcp-pricing-agent .
FROM python:3.12-slim

# Reasoning: chromadb's default embedding function runs MiniLM through onnxruntime,
# which dynamically links libgomp (OpenMP). The slim base image does not ship it, so
# retrieval would fail at import time on the first query without this.
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Reasoning: Copy requirements first so the (slow) pip layer is cached and only
# reinstalls when dependencies actually change, not on every source edit.
COPY requirements-agent.txt .
RUN pip install --no-cache-dir -r requirements-agent.txt

# Reasoning: An agent image gets exactly three things — the shared RAG layer (retriever
# plus the ingested Chroma store), the transport switch, and its own agent code. It
# deliberately does NOT get the orchestrator, the Mistral SDK, or the API key: an agent
# server never calls a model, so it has no business holding LLM credentials. That
# isolation is the security argument for one-container-per-agent, not just tidiness.
COPY rag/ ./rag/
COPY shared/__init__.py shared/mcp_transport.py ./shared/
COPY agents/__init__.py ./agents/
COPY agents/pricing_agent/ ./agents/pricing_agent/

ENV MCP_TRANSPORT=http \
    MCP_PORT=8001 \
    PYTHONUNBUFFERED=1

# Reasoning: Run from the agent's own directory — server.py does `from tools import ...`,
# a bare import that only resolves when the agent directory is the working directory.
# This mirrors exactly how the agent runs standalone outside Docker.
WORKDIR /app/agents/pricing_agent

EXPOSE 8001
CMD ["python", "server.py"]
