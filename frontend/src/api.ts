import type { QueryResponse } from "./types";

// Reasoning: The orchestrator's FastAPI server defaults to port 8000 (see
// orchestrator/main.py). Overridable via VITE_API_URL for Docker/deployed setups
// where the frontend and orchestrator aren't both on localhost.
const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export async function runQuery(query: string): Promise<QueryResponse> {
  const res = await fetch(`${API_URL}/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query }),
  });

  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(`Orchestrator returned ${res.status}${detail ? `: ${detail}` : ""}`);
  }

  return res.json();
}
