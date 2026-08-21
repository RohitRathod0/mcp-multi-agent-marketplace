# Risk & Support Agent — standalone MCP server image.
# Build from the PROJECT ROOT, not this directory:
#   docker build -f agents/risk_support_agent/Dockerfile -t mcp-risk-support-agent .
FROM python:3.12-slim

# Reasoning: chromadb's default embedding function runs MiniLM through onnxruntime,
# which dynamically links libgomp (OpenMP) and is absent from the slim base image.
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Reasoning: Requirements first, so the slow pip layer stays cached across source edits.
COPY requirements-agent.txt .
RUN pip install --no-cache-dir -r requirements-agent.txt

# Reasoning: Shared RAG layer + transport switch + this agent only — no orchestrator,
# no Mistral SDK, no API key. See agents/pricing_agent/Dockerfile for the full rationale.
COPY rag/ ./rag/
COPY shared/__init__.py shared/mcp_transport.py ./shared/
COPY agents/__init__.py ./agents/
COPY agents/risk_support_agent/ ./agents/risk_support_agent/

ENV MCP_TRANSPORT=http \
    MCP_PORT=8003 \
    PYTHONUNBUFFERED=1

# Reasoning: server.py does `from tools import ...`, which only resolves from the
# agent's own directory — same as running it standalone.
WORKDIR /app/agents/risk_support_agent

EXPOSE 8003
CMD ["python", "server.py"]
