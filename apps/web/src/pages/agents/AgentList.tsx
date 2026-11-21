import { notifications } from "@mantine/notifications";
import {
  RiDeleteBin6Line,
  RiImageAddLine,
  RiImageCircleLine,
  RiRobot2Line,
} from "@remixicon/react";
import { useState } from "react";

import type { Agent } from "../../api/endpoints";
import {
  useDeleteAgent,
  useResetAvatar,
  useUploadAvatar,
} from "../../api/queries";
import { AgentAvatar } from "../../components/agents/AgentAvatar";
import { DataTable } from "../../design-system/data/DataTable";
import { IconButton } from "../../design-system/icons/IconButton";
import { ConfirmDialog } from "../../design-system/overlays/ConfirmDialog";
import { Badge } from "../../design-system/primitives/Badge";
import { Button } from "../../design-system/primitives/Button";
import { GuidedEmptyState } from "../../design-system/patterns/GuidedEmptyState";
import { AgentCardModal } from "./AgentCardModal";
import styles from "./agents.module.css";

export function AgentList({
  agents,
  onNew,
}: {
  agents: Agent[];
  onNew: () => void;
}) {
  const del = useDeleteAgent();
  const upload = useUploadAvatar();
  const reset = useResetAvatar();
  const [versions, setVersions] = useState<Record<string, number>>({});
  const [cardAgent, setCardAgent] = useState<string | null>(null);
  const [agentToDelete, setAgentToDelete] = useState<Agent | null>(null);

  async function uploadPhoto(name: string, file: File | undefined) {
    if (!file) return;
    try {
      await upload.mutateAsync({ name, file });
      setVersions((v) => ({ ...v, [name]: (v[name] ?? 0) + 1 }));
    } catch {
      notifications.show({ message: "Failed to upload photo", color: "red" });
    }
  }

  async function removePhoto(name: string) {
    await reset.mutateAsync(name);
    setVersions((v) => ({ ...v, [name]: (v[name] ?? 0) + 1 }));
  }

  if (agents.length === 0) {
    return (
      <GuidedEmptyState
        icon={RiRobot2Line}
        title="No agents"
        description="Configure an agent with a model, instructions, and tools."
        helpId="agent.tools"
        action={<Button onClick={onNew}>Create your first agent</Button>}
      />
    );
  }

  return (
    <>
      <DataTable<Agent>
        rowKey={(agent) => agent.name}
        rows={agents}
        columns={[
          {
            key: "agent",
            header: "Agent",
            render: (agent) => (
              <div className={styles.agentCell}>
                <AgentAvatar name={agent.name} version={versions[agent.name] ?? 0} />
                <div>
                  <strong>{agent.name}</strong>
                  <span>{agent.description}</span>
                </div>
              </div>
            ),
          },
          {
            key: "model",
            header: "Model",
            render: (agent) => (
              <code>{agent.model_label ?? agent.model_binding.model}</code>
            ),
          },
          {
            key: "tools",
            header: "Tools",
            render: (agent) => (
              <Badge>{agent.tool_bindings?.length ?? 0} bindings</Badge>
            ),
          },
          {
            key: "actions",
            header: "Actions",
            render: (agent) => (
              <div className={styles.actions}>
                <input
                  id={`avatar-${agent.name}`}
                  type="file"
                  accept="image/png,image/jpeg,image/webp"
                  aria-label={`Change photo ${agent.name}`}
                  hidden
                  onChange={(e) =>
                    uploadPhoto(agent.name, e.currentTarget.files?.[0])
                  }
                />
                <IconButton
                  label="Change photo"
                  icon={RiImageAddLine}
                  size={16}
                  onClick={() => document.getElementById(`avatar-${agent.name}`)?.click()}
                />
                <IconButton
                  label="Remove photo"
                  icon={RiImageCircleLine}
                  size={16}
                  onClick={() => removePhoto(agent.name)}
                />
                <IconButton
                  label="A2A"
                  icon={RiRobot2Line}
                  size={16}
                  onClick={() => setCardAgent(agent.name)}
                />
                <IconButton
                  label="Delete"
                  icon={RiDeleteBin6Line}
                  size={16}
                  color="red"
                  onClick={() => setAgentToDelete(agent)}
                />
              </div>
            ),
          },
        ]}
      />
      {cardAgent && (
        <AgentCardModal name={cardAgent} onClose={() => setCardAgent(null)} />
      )}
      <ConfirmDialog
        opened={agentToDelete !== null}
        title="Delete agent?"
        description={`Delete "${agentToDelete?.name ?? ""}" permanently? This cannot be undone.`}
        requireText={agentToDelete?.name}
        confirmLabel="Delete"
        danger
        onConfirm={async () => {
          if (!agentToDelete) return;
          await del.mutateAsync(agentToDelete.name);
          setAgentToDelete(null);
        }}
        onClose={() => setAgentToDelete(null)}
      />
    </>
  );
}

