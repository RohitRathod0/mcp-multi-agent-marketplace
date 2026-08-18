import type { AgentName, ToolCallTrace } from "../types";

// Reasoning: This panel is the whole point of the demo — it makes the orchestrator's
// multi-agent routing visible. Every tool call in a turn (possibly spanning 2-3
// independent agent servers) is rendered in call order so a viewer can see, e.g., a
// pricing + inventory query actually reach both agents instead of just trusting the
// final prose answer.

const AGENT_LABEL: Record<AgentName, string> = {
  pricing: "Pricing",
  inventory: "Inventory",
  risk_support: "Risk & Support",
  none: "None",
  unknown: "Unknown",
};

function agentColorVar(agent: AgentName): string {
  return `var(--agent-${agent})`;
}

interface Props {
  toolCalls: ToolCallTrace[] | null;
  loading: boolean;
}

export default function AgentTraceViewer({ toolCalls, loading }: Props) {
  return (
    <aside className="trace-panel">
      <div className="trace-header">
        <h2>Agent Trace</h2>
        <p>Which MCP agent server(s) handled the last query, in call order.</p>
      </div>
      <div className="trace-scroll">
        {loading && <div className="trace-empty">Running tool calls…</div>}
        {!loading && (!toolCalls || toolCalls.length === 0) && (
          <div className="trace-empty">
            No tool calls yet — ask a question to see which agents get invoked.
          </div>
        )}
        {!loading &&
          toolCalls &&
          toolCalls.map((call, idx) => (
            <div className="trace-step" key={idx}>
              <div className="trace-dot" style={{ background: agentColorVar(call.agent) }}>
                {idx + 1}
              </div>
              <div className="trace-card">
                <div className="trace-agent-row">
                  <span className="agent-badge" style={{ background: agentColorVar(call.agent) }}>
                    {AGENT_LABEL[call.agent] ?? call.agent}
                  </span>
                  <span className="trace-tool">{call.tool}()</span>
                </div>
                {Object.keys(call.args).length > 0 && (
                  <div className="trace-args">
                    {Object.entries(call.args)
                      .map(([k, v]) => `${k}="${v}"`)
                      .join("  ")}
                  </div>
                )}
                <div className="trace-result">{call.result}</div>
              </div>
            </div>
          ))}
      </div>
    </aside>
  );
}
