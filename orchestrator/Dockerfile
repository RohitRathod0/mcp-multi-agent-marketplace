# Orchestrator — FastAPI + LangGraph router, and the MCP *client* for all three agents.
# Build from the PROJECT ROOT:
#   docker build -f orchestrator/Dockerfile -t mcp-orchestrator .
FROM python:3.12-slim

WORKDIR /app

# Reasoning: Requirements first so the pip layer caches independently of source edits.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Reasoning: The orchestrator needs the router, the prompts, and shared/ (config +
# Mistral retry helpers). It does NOT copy agents/ — under MCP_TRANSPORT=http it reaches
# the agents over the network, so having their source here would be dead weight that
# also blurs the separation the architecture is meant to demonstrate.
COPY orchestrator/ ./orchestrator/
COPY shared/ ./shared/

ENV MCP_TRANSPORT=http \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

EXPOSE 8000

# Reasoning: uvicorn directly rather than `python orchestrator/main.py` so the bind host
# and worker behaviour are explicit in the process command. Single worker is deliberate:
# MCPAgentPool holds one persistent MCP session per agent in a background event loop, so
# multiple workers would each open their own duplicate set of agent connections.
CMD ["uvicorn", "orchestrator.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
