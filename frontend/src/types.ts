// Reasoning: Mirrors orchestrator/main.py's QueryResponse / ToolCallTrace Pydantic
// models exactly, so the frontend and backend never drift silently out of sync.

export type AgentName = "pricing" | "inventory" | "risk_support" | "unknown" | "none";

export interface ToolCallTrace {
  agent: AgentName;
  tool: string;
  args: Record<string, string>;
  result: string;
}

export interface QueryResponse {
  answer: string;
  agent_called: string;
  tool_result: string;
  tool_calls: ToolCallTrace[];
}

export interface ChatTurn {
  id: string;
  query: string;
  response: QueryResponse | null;
  error: string | null;
  loading: boolean;
}
