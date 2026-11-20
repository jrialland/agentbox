export function InlineError({ children }: { children: string }) {
  return (
    <p role="alert" style={{ color: "var(--ab-danger)", margin: 0 }}>
      {children}
    </p>
  );
}
