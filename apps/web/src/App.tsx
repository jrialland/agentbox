import { MantineProvider } from "@mantine/core";
import { ModalsProvider } from "@mantine/modals";
import { Notifications } from "@mantine/notifications";

import { ThemeSync } from "./theme/ThemeSync";

export function App() {
  return (
    <MantineProvider defaultColorScheme="auto">
      <ThemeSync />
      <Notifications />
      <ModalsProvider>
        <div>Agentbox</div>
      </ModalsProvider>
    </MantineProvider>
  );
}
