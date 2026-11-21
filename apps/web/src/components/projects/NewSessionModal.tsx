import { Modal } from "@mantine/core";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { ApiError } from "../../api/errors";
import { useAgents, useCreateSession } from "../../api/queries";
import { FormField } from "../../design-system/forms/FormField";
import { Select } from "../../design-system/forms/Select";
import { Button } from "../../design-system/primitives/Button";
import { firstFieldError } from "../../lib/validation";

export function NewSessionModal({
  opened,
  onClose,
  projectId,
}: {
  opened: boolean;
  onClose: () => void;
  projectId: string;
}) {
  const [agentName, setAgentName] = useState<string | null>(null);
  const [errors, setErrors] = useState<{ agent?: string }>({});
  const [formError, setFormError] = useState<string | null>(null);
  const { data: agents } = useAgents();
  const create = useCreateSession();
  const navigate = useNavigate();

  async function submit() {
    if (!agentName) {
      setErrors({ agent: "Choose an agent to create a session." });
      return;
    }
    setErrors({});
    setFormError(null);
    try {
      const session = await create.mutateAsync({
        project_id: projectId,
        agent_id: agentName,
      });
      onClose();
      navigate(`/sessions/${session.id}`);
    } catch (caught) {
      if (caught instanceof ApiError) {
        const agentError = firstFieldError(caught.fields, "agent_id");
        if (agentError) {
          setErrors({ agent: agentError });
        } else {
          setFormError(caught.detail);
        }
      } else {
        setFormError(caught instanceof Error ? caught.message : "Request failed.");
      }
    }
  }

  return (
    <Modal opened={opened} onClose={onClose} title="New session">
      <FormField label="Agent" required error={errors.agent}>
        <Select
          aria-label="Agent"
          data={(agents ?? []).map((a) => a.name)}
          value={agentName}
          onChange={setAgentName}
        />
      </FormField>
      {!agentName && (
        <p role="alert">Choose an agent to create a session.</p>
      )}
      {formError && <p role="alert">{formError}</p>}
      <Button
        mt="md"
        onClick={submit}
        loading={create.isPending}
        disabled={!agentName}
      >
        Create
      </Button>
    </Modal>
  );
}
