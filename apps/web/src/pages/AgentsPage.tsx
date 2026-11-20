import { RiAddLine } from "@remixicon/react";
import { useState } from "react";

import { useAgents } from "../api/queries";
import { ListPage } from "../design-system/patterns/ListPage";
import { Button } from "../design-system/primitives/Button";
import { AgentCreateDrawer } from "./agents/AgentCreateDrawer";
import { AgentList } from "./agents/AgentList";

export const NATIVE_TOOLS = [
  "read_text_file",
  "read_media_file",
  "read_multiple_files",
  "list_directory",
  "list_directory_with_sizes",
  "directory_tree",
  "search_files",
  "get_file_info",
  "list_allowed_directories",
  "write_file",
  "append_file",
  "edit_file",
  "create_directory",
  "move_file",
  "copy_file",
  "delete_path",
  "web_search",
  "fetch_url",
  "terminal",
];

export const TERMINAL_TOOLS = [
  "run_command",
  "list_jobs",
  "get_job_output",
  "kill_job",
];

export function buildToolBindings(tools: string[]) {
  return tools.flatMap((tool) =>
    tool === "terminal"
      ? TERMINAL_TOOLS.map((name) => ({ name }))
      : [{ name: tool }],
  );
}

export function AgentsPage() {
  const { data: agents } = useAgents();
  const [createOpen, setCreateOpen] = useState(false);
  const agentList = agents ?? [];

  return (
    <ListPage
      title="Agents"
      subtitle={`${agentList.length} configured`}
      actions={
        <Button
          leftSection={<RiAddLine size={16} />}
          onClick={() => setCreateOpen(true)}
        >
          New agent
        </Button>
      }
    >
      <AgentList agents={agentList} onNew={() => setCreateOpen(true)} />
      <AgentCreateDrawer
        opened={createOpen}
        onClose={() => setCreateOpen(false)}
        subAgentOptions={agentList.map((agent) => agent.name)}
      />
    </ListPage>
  );
}
