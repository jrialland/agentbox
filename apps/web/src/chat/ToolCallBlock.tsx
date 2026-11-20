import type { Segment } from "./segments";

type ToolSegment = Extract<Segment, { kind: "tool" }>;

export function ToolCallBlock({ call }: { call: ToolSegment }) {
  return (
    <details className="tool-call">
      <summary>Tool: {call.name}</summary>
      <pre>args: {call.args}</pre>
      {call.result !== undefined && <pre>result: {call.result}</pre>}
    </details>
  );
}
