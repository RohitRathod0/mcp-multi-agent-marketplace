import { useEffect, useRef } from "react";
import type { ChatTurn } from "../types";

const EXAMPLE_QUERIES = [
  "What is the baseline price for the iphone-15?",
  "Is the iphone-15 in stock, and is now a good time to discount it for clearance?",
  "Assess the risk level for seller techworld-99.",
  "A customer says order ORD-4409 never arrived — what should I do?",
];

interface Props {
  turns: ChatTurn[];
  onSend: (query: string) => void;
  input: string;
  onInputChange: (value: string) => void;
  busy: boolean;
}

export default function ChatWindow({ turns, onSend, input, onInputChange, busy }: Props) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [turns]);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = input.trim();
    if (!trimmed || busy) return;
    onSend(trimmed);
  }

  return (
    <section className="chat-panel">
      <div className="chat-scroll" ref={scrollRef}>
        {turns.length === 0 && (
          <div className="empty-state">
            <p>
              Ask the orchestrator a marketplace question. It routes across the pricing,
              inventory, and risk/support agents (real MCP servers) and combines their
              answers.
            </p>
            <div className="example-chips">
              {EXAMPLE_QUERIES.map((q) => (
                <button key={q} className="chip" onClick={() => onSend(q)} disabled={busy}>
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}

        {turns.map((turn) => (
          <div className="turn" key={turn.id}>
            <div className="bubble user">{turn.query}</div>
            {turn.loading && (
              <div className="bubble assistant">
                <span className="typing">
                  <span></span>
                  <span></span>
                  <span></span>
                </span>
              </div>
            )}
            {turn.error && <div className="bubble assistant error">{turn.error}</div>}
            {turn.response && <div className="bubble assistant">{turn.response.answer}</div>}
          </div>
        ))}
      </div>

      <form className="composer" onSubmit={handleSubmit}>
        <input
          type="text"
          placeholder="Ask about pricing, inventory, or seller risk…"
          value={input}
          onChange={(e) => onInputChange(e.target.value)}
          disabled={busy}
        />
        <button type="submit" disabled={busy || !input.trim()}>
          Send
        </button>
      </form>
    </section>
  );
}
