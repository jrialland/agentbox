import { MantineProvider } from "@mantine/core";
import { render } from "@testing-library/react";

import { AgentAvatar } from "./AgentAvatar";

test("renders the avatar image with the agent name and version", () => {
  const { container } = render(
    <MantineProvider>
      <AgentAvatar name="bot" version={2} />
    </MantineProvider>,
  );
  const img = container.querySelector("img");
  expect(img?.getAttribute("src")).toContain("/agents/bot/avatar?v=2");
});
