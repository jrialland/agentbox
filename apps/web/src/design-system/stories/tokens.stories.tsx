import type { Meta, StoryObj } from "@storybook/react-vite";

const colors = [
  "canvas",
  "surface",
  "surface-raised",
  "border",
  "text",
  "text-muted",
  "phosphor",
  "amber",
  "cyan",
  "magenta",
  "danger",
] as const;

function TokenReference() {
  return (
    <div style={{ display: "grid", gap: 32 }}>
      <section>
        <h1 style={{ fontFamily: "var(--ab-font-display)", fontSize: 24 }}>
          [AGENTBOX]▮
        </h1>
        <p style={{ fontFamily: "var(--ab-font-body)" }}>
          Inter body text. The quick brown fox jumps over the lazy agent.
        </p>
        <p style={{ fontFamily: "var(--ab-font-mono)" }}>
          session_cffa8f32 · 12:04:11 · 1.2k tokens
        </p>
      </section>
      <section
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))",
          gap: 12,
        }}
      >
        {colors.map((name) => (
          <div
            key={name}
            style={{ border: "1px solid var(--ab-border)", padding: 12 }}
          >
            <div
              style={{
                height: 48,
                background: `var(--ab-${name})`,
                border: "1px solid var(--ab-border)",
              }}
            />
            <strong style={{ fontFamily: "var(--ab-font-mono)", fontSize: 12 }}>
              {name}
            </strong>
            <div
              style={{
                fontFamily: "var(--ab-font-mono)",
                fontSize: 11,
                color: "var(--ab-text-muted)",
              }}
            >
              var(--ab-{name})
            </div>
          </div>
        ))}
      </section>
    </div>
  );
}

const meta: Meta<typeof TokenReference> = {
  title: "Foundations/Tokens",
  component: TokenReference,
};

export default meta;
type Story = StoryObj<typeof TokenReference>;
export const Default: Story = {};
