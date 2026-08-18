import { useState } from "react";
import ChatWindow from "./components/ChatWindow";
import AgentTraceViewer from "./components/AgentTraceViewer";
import { runQuery } from "./api";
import type { ChatTurn } from "./types";

export default function App() {
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [input, setInput] = useState("");

  const busy = turns.some((t) => t.loading);
  const latestTurn = turns[turns.length - 1];

  async function handleSend(query: string) {
    const id = crypto.randomUUID();
    setTurns((prev) => [...prev, { id, query, response: null, error: null, loading: true }]);
    setInput("");

    try {
      const response = await runQuery(query);
      setTurns((prev) =>
        prev.map((t) => (t.id === id ? { ...t, response, loading: false } : t))
      );
    } catch (err) {
      setTurns((prev) =>
        prev.map((t) =>
          t.id === id
            ? {
                ...t,
                error:
                  err instanceof Error
                    ? `Couldn't reach the orchestrator: ${err.message}`
                    : "Couldn't reach the orchestrator.",
                loading: false,
              }
            : t
        )
      );
    }
  }

  return (
    <div className="app">
      <header className="app-header">
        <h1>MCP Marketplace Orchestrator</h1>
        <p>Multi-agent routing over pricing, inventory, and risk/support MCP servers.</p>
      </header>
      <div className="app-body">
        <ChatWindow
          turns={turns}
          onSend={handleSend}
          input={input}
          onInputChange={setInput}
          busy={busy}
        />
        <AgentTraceViewer
          toolCalls={latestTurn?.response?.tool_calls ?? null}
          loading={Boolean(latestTurn?.loading)}
        />
      </div>
    </div>
  );
}
