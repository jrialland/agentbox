import { RiAddLine } from "@remixicon/react";
import { useState } from "react";

import type { Agent } from "../api/endpoints";
import { useAgents } from "../api/queries";
import { ErrorState } from "../design-system/patterns/ErrorState";
import { ListPage } from "../design-system/patterns/ListPage";
import { Button } from "../design-system/primitives/Button";
import { AgentFormDrawer } from "./agents/AgentFormDrawer";
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

type EditorState =
  | { mode: "create" }
  | { mode: "edit"; agent: Agent }
  | null;

export function AgentsPage() {
  const { data: agents, error, refetch } = useAgents();
  const [editor, setEditor] = useState<EditorState>(null);
  const [editorKey, setEditorKey] = useState(0);
  const agentList = agents ?? [];

  function openEditor(next: Exclude<EditorState, null>) {
    setEditor(next);
    setEditorKey((key) => key + 1);
  }

  if (error) {
    return (
      <ErrorState
        title="Could not load agents"
        message={error.message}
        onRetry={() => void refetch()}
      />
    );
  }

  return (
    <ListPage
      title="Agents"
      subtitle={`${agentList.length} configured`}
      actions={
        <Button
          leftSection={<RiAddLine size={16} />}
          onClick={() => openEditor({ mode: "create" })}
        >
          New agent
        </Button>
      }
    >
      <AgentList
        agents={agentList}
        onNew={() => openEditor({ mode: "create" })}
        onEdit={(agent) => openEditor({ mode: "edit", agent })}
      />
      <AgentFormDrawer
        key={editorKey}
        opened={editor !== null}
        onClose={() => setEditor(null)}
        agent={editor?.mode === "edit" ? editor.agent : undefined}
      />
    </ListPage>
  );
}
