export function ReasoningBlock({ content }: { content: string }) {
  return (
    <details className="reasoning-block">
      <summary>Reasoning</summary>
      <pre>{content}</pre>
    </details>
  );
}
