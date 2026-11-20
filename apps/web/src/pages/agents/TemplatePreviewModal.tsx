import { useState } from "react";

import { usePreviewPrompt } from "../../api/queries";
import { TextInput } from "../../design-system/forms/TextInput";
import { Textarea } from "../../design-system/forms/Textarea";
import { Modal } from "../../design-system/overlays/Modal";
import { Button } from "../../design-system/primitives/Button";

export function TemplatePreviewModal({
  initialTemplate,
  onApply,
  onClose,
}: {
  initialTemplate: string;
  onApply: (template: string) => void;
  onClose: () => void;
}) {
  const preview = usePreviewPrompt();
  const [template, setTemplate] = useState(initialTemplate);
  const [context, setContext] = useState<Record<string, string>>({});
  const [result, setResult] = useState<{
    rendered: string;
    missing: string[];
    error: { message: string; line?: number | null } | null;
    variables: string[];
  } | null>(null);

  async function renderNow() {
    const data = await preview.mutateAsync({ template, context });
    setContext(data.context);
    setResult(data);
  }

  return (
    <Modal opened onClose={onClose} title="Test prompt template" size="xl">
      <Textarea
        label="Template"
        minRows={6}
        value={template}
        onChange={(e) => setTemplate(e.currentTarget.value)}
      />
      <Button mt="sm" onClick={renderNow} loading={preview.isPending}>
        Render
      </Button>
      {result && (
        <>
          {result.error && (
            <div role="alert" style={{ color: "var(--ab-danger)" }}>
              {result.error.message}
              {result.error.line ? ` (line ${result.error.line})` : ""}
            </div>
          )}
          {result.missing.length > 0 && (
            <div role="status" style={{ color: "var(--ab-amber)" }}>
              Missing: {result.missing.join(", ")}
            </div>
          )}
          <Textarea
            label="Rendered"
            minRows={6}
            readOnly
            value={result.rendered}
            mt="sm"
          />
          {result.variables.map((path) => (
            <TextInput
              key={path}
              label={path}
              value={context[path] ?? ""}
              onChange={(e) => {
                const value = e.currentTarget.value;
                setContext((prev) => ({ ...prev, [path]: value }));
              }}
            />
          ))}
        </>
      )}
      <Button
        mt="md"
        onClick={() => {
          onApply(template);
          onClose();
        }}
      >
        Apply to instructions
      </Button>
    </Modal>
  );
}
