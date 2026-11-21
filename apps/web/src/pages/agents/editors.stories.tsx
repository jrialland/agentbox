import type { Meta, StoryObj } from "@storybook/react-vite";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";

import { HelpProvider } from "../../help/HelpProvider";
import { Textarea } from "../../design-system/forms/Textarea";
import { AgentCardModal } from "./AgentCardModal";
import { AgentModesEditor } from "./AgentModesEditor";
import { AgentToolsEditor } from "./AgentToolsEditor";
import type { AgentMode } from "./agentFormValidation";

const meta: Meta = { title: "Agents/Editors" };
export default meta;

function ToolsStory() {
  const [value, setValue] = useState<string[]>(["read_text_file", "list_directory"]);
  return (
    <HelpProvider>
      <AgentToolsEditor value={value} onChange={setValue} />
    </HelpProvider>
  );
}

function ModesStory() {
  const [value, setValue] = useState<AgentMode[]>([
    { name: "ask", write: false },
    { name: "agent", write: true },
  ]);
  return (
    <HelpProvider>
      <AgentModesEditor value={value} onChange={setValue} />
    </HelpProvider>
  );
}

function A2AStory() {
  const client = new QueryClient();
  client.setQueryData(["agent-card", "Reviewer"], {
    name: "Reviewer",
    description: "Reviews code and summarizes risks.",
    version: "1.0.0",
    capabilities: { streaming: true },
    defaultInputModes: ["text/plain"],
    defaultOutputModes: ["text/plain"],
    skills: [
      {
        id: "code-review",
        name: "Code review",
        description: "Review a change and list risks.",
        tags: ["review", "code"],
        examples: ["Review this diff"],
      },
    ],
  });
  return (
    <QueryClientProvider client={client}>
      <HelpProvider>
        <AgentCardModal name="Reviewer" onClose={() => {}} />
      </HelpProvider>
    </QueryClientProvider>
  );
}

export const Tools: StoryObj = { render: () => <ToolsStory /> };
export const Modes: StoryObj = { render: () => <ModesStory /> };
export const A2AStructured: StoryObj = { render: () => <A2AStory /> };
export const A2AJson: StoryObj = {
  render: () => (
    <Textarea
      label="Agent card JSON"
      minRows={16}
      defaultValue={'{\n  "name": "Reviewer",\n  "version": "1.0.0",\n  "skills": []\n}'}
    />
  ),
};
