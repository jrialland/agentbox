import { Button, Modal, Select } from "@mantine/core";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { useAgents, useCreateSession } from "../../api/queries";

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
  const { data: agents } = useAgents();
  const create = useCreateSession();
  const navigate = useNavigate();

  async function submit() {
    if (!agentName) return;
    const session = await create.mutateAsync({ project_id: projectId, agent_id: agentName });
    onClose();
    navigate(`/sessions/${session.id}`);
  }

  return (
    <Modal opened={opened} onClose={onClose} title="New session">
      <Select
        label="Agent"
        data={(agents ?? []).map((a) => a.name)}
        value={agentName}
        onChange={setAgentName}
      />
      <Button mt="md" onClick={submit} loading={create.isPending}>
        Create
      </Button>
    </Modal>
  );
}
