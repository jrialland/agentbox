import {
  RiAddLine,
  RiArrowRightLine,
  RiChat3Line,
  RiFolderLine,
  RiRobot2Line,
} from "@remixicon/react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { useAgents, useProjects, useSessions } from "../api/queries";
import { NewProjectModal } from "../components/projects/NewProjectModal";
import { Button } from "../design-system/primitives/Button";
import { DashboardCard } from "../design-system/patterns/DashboardCard";
import { EmptyStatePanel } from "../design-system/patterns/EmptyStatePanel";
import { PageContainer } from "../design-system/shell/PageContainer";
import { PageHeader } from "../design-system/primitives/PageHeader";
import { Panel } from "../design-system/primitives/Panel";
import styles from "./home.module.css";

export function HomePage() {
  const { data: projects } = useProjects();
  const { data: sessions } = useSessions();
  const { data: agents } = useAgents();
  const [projectOpen, setProjectOpen] = useState(false);
  const navigate = useNavigate();

  const projectList = projects ?? [];
  const sessionList = sessions ?? [];
  const agentList = agents ?? [];
  const recentSessions = [...sessionList]
    .sort((a, b) => (b.created_at ?? "").localeCompare(a.created_at ?? ""))
    .slice(0, 6);

  function projectName(projectId: string) {
    return (
      projectList.find((project) => project.id === projectId)?.name ?? projectId
    );
  }

  return (
    <PageContainer>
      <PageHeader
        title="Home"
        subtitle="Agentbox operator console"
        actions={
          <>
            <Button
              leftSection={<RiAddLine size={16} />}
              onClick={() => setProjectOpen(true)}
            >
              New project
            </Button>
            <Button
              onClick={() => navigate("/agents")}
              variant="light"
              rightSection={<RiArrowRightLine size={16} />}
            >
              View agents
            </Button>
          </>
        }
      />

      <section className={`${styles.hero} ab-scanlines`}>
        <div className={styles.heroBrand}>[AGENTBOX]▮</div>
        <p className={styles.heroKicker}>agentic work, under your control</p>
        <h2>Build, run, and supervise agents from one console.</h2>
        <div className={styles.heroActions}>
          <Button onClick={() => setProjectOpen(true)}>Start a session</Button>
          <Button onClick={() => navigate("/providers")} variant="light">
            Configure providers
          </Button>
        </div>
      </section>

      <div className={styles.stats}>
        <DashboardCard
          label="Projects"
          value={projectList.length}
          hint="workspaces"
          icon={<RiFolderLine size={18} />}
        />
        <DashboardCard
          label="Sessions"
          value={sessionList.length}
          hint="across all projects"
          icon={<RiChat3Line size={18} />}
        />
        <DashboardCard
          label="Agents"
          value={agentList.length}
          hint="configured"
          icon={<RiRobot2Line size={18} />}
        />
      </div>

      <div className={styles.columns}>
        <Panel>
          <Panel.Header>
            <span>Recent sessions</span>
          </Panel.Header>
          <Panel.Body>
            {recentSessions.length === 0 ? (
              <EmptyStatePanel
                icon={RiChat3Line}
                title="No sessions yet"
                description="Create a project and start a session to see activity here."
                action={
                  <Button onClick={() => setProjectOpen(true)}>
                    New project
                  </Button>
                }
              />
            ) : (
              <ul className={styles.sessionList}>
                {recentSessions.map((session) => (
                  <li key={session.id} className={styles.sessionRow}>
                    <Link to={`/sessions/${session.id}`}>
                      <strong>{session.agent_id}</strong>
                      <span>{projectName(session.project_id)}</span>
                    </Link>
                    <IconLink sessionId={session.id} />
                  </li>
                ))}
              </ul>
            )}
          </Panel.Body>
        </Panel>

        <Panel>
          <Panel.Header>
            <span>Projects</span>
          </Panel.Header>
          <Panel.Body>
            {projectList.length === 0 ? (
              <EmptyStatePanel
                icon={RiFolderLine}
                title="No projects"
                description="Create a project to group sessions by workspace."
                action={
                  <Button onClick={() => setProjectOpen(true)}>
                    New project
                  </Button>
                }
              />
            ) : (
              <ul className={styles.projectList}>
                {projectList.map((project) => (
                  <li key={project.id}>
                    <span>{project.name}</span>
                    <code>{project.path}</code>
                  </li>
                ))}
              </ul>
            )}
          </Panel.Body>
        </Panel>
      </div>

      <NewProjectModal
        opened={projectOpen}
        onClose={() => setProjectOpen(false)}
      />
    </PageContainer>
  );
}

function IconLink({ sessionId }: { sessionId: string }) {
  return (
    <Link
      to={`/sessions/${sessionId}`}
      aria-label="Open session"
      className={styles.iconLink}
    >
      <RiArrowRightLine size={18} />
    </Link>
  );
}

