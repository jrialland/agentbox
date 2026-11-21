import { ModalsProvider } from "@mantine/modals";
import { Notifications } from "@mantine/notifications";
import { QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes } from "react-router-dom";

import { createQueryClient } from "./api/queryClient";
import { RequireAuth } from "./components/auth/RequireAuth";
import { ThemeProvider } from "./design-system/theme/ThemeProvider";
import { HelpProvider } from "./help/HelpProvider";
import { CommandShell } from "./design-system/shell/CommandShell";
import { AdminPage } from "./pages/AdminPage";
import { AgentsPage } from "./pages/AgentsPage";
import { ApiKeysPage } from "./pages/ApiKeysPage";
import { HomePage } from "./pages/HomePage";
import { LoginPage } from "./pages/LoginPage";
import { NotFoundPage } from "./pages/NotFoundPage";
import { ProvidersPage } from "./pages/ProvidersPage";
import { SessionPage } from "./pages/SessionPage";
import { SkillsPage } from "./pages/SkillsPage";

const queryClient = createQueryClient();

export function App() {
  return (
    <ThemeProvider>
      <HelpProvider>
      <Notifications />
      <ModalsProvider>
        <QueryClientProvider client={queryClient}>
          <BrowserRouter>
            <Routes>
              <Route path="/login" element={<LoginPage />} />
              <Route element={<RequireAuth />}>
                <Route element={<CommandShell />}>
                  <Route index element={<HomePage />} />
                  <Route path="admin" element={<AdminPage />} />
                  <Route path="agents" element={<AgentsPage />} />
                  <Route path="api-keys" element={<ApiKeysPage />} />
                  <Route path="providers" element={<ProvidersPage />} />
                  <Route path="skills" element={<SkillsPage />} />
                  <Route path="sessions/:id" element={<SessionPage />} />
                  <Route path="*" element={<NotFoundPage />} />
                </Route>
              </Route>
            </Routes>
          </BrowserRouter>
        </QueryClientProvider>
      </ModalsProvider>
      </HelpProvider>
    </ThemeProvider>
  );
}

