import type { ToolCall } from "./useChat";

export function ToolCallBlock({ call }: { call: ToolCall }) {
  return (
    <details className="tool-call">
      <summary>Tool: {call.name}</summary>
      <pre>args: {call.args}</pre>
      {call.result !== undefined && <pre>result: {call.result}</pre>}
    </details>
  );
}
