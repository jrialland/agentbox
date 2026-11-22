import {
  RiAddLine,
  RiArrowRightLine,
  RiChat3Line,
  RiFolderLine,
  RiRobot2Line,
} from "@remixicon/react";
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { useAgents, useModels, useProjects, useProviders, useSessions } from "../api/queries";
import { NewProjectModal } from "../components/projects/NewProjectModal";
import { Button } from "../design-system/primitives/Button";
import { DashboardCard } from "../design-system/patterns/DashboardCard";
import { EmptyStatePanel } from "../design-system/patterns/EmptyStatePanel";
import { ErrorState } from "../design-system/patterns/ErrorState";
import { PageContainer } from "../design-system/shell/PageContainer";
import { PageHeader } from "../design-system/primitives/PageHeader";
import { Wordmark } from "../design-system/primitives/Wordmark";
import { HomeChecklist } from "../onboarding/HomeChecklist";
import { OnboardingWizard } from "../onboarding/OnboardingWizard";
import {
  deriveOnboardingProgress,
  type OnboardingStep,
} from "../onboarding/onboardingProgress";
import { useOnboardingPreference } from "../onboarding/useOnboardingPreference";
import { sessionTitle } from "../lib/sessionTitle";
import { Panel } from "../design-system/primitives/Panel";
import styles from "./home.module.css";

export function HomePage() {
  const {
    data: projects,
    error: projectsError,
    refetch: refetchProjects,
  } = useProjects();
  const {
    data: sessions,
    error: sessionsError,
    refetch: refetchSessions,
  } = useSessions();
  const { data: agents, error: agentsError, refetch: refetchAgents } = useAgents();
  const {
    data: providers,
    error: providersError,
    refetch: refetchProviders,
  } = useProviders();
  const {
    data: models,
    error: modelsError,
    refetch: refetchModels,
  } = useModels();
  const [projectOpen, setProjectOpen] = useState(false);
  const [wizardOpen, setWizardOpen] = useState(false);
  const [wizardStep, setWizardStep] = useState<OnboardingStep>("welcome");
  const navigate = useNavigate();
  const { dismissed, dismiss, reset } = useOnboardingPreference();

  const projectList = projects ?? [];
  const sessionList = sessions ?? [];
  const agentList = agents ?? [];
  const snapshot = {
    providers: providers?.length ?? 0,
    models: models?.length ?? 0,
    agents: agentList.length,
    sessions: sessionList.length,
  };
  const progress = deriveOnboardingProgress(snapshot);
  const setupLoaded = providers !== undefined && agents !== undefined;

  useEffect(() => {
    if (!setupLoaded || providersError || agentsError) return;
    if (snapshot.providers === 0 && snapshot.agents === 0 && !dismissed) {
      setWizardOpen(true);
    }
  }, [
    setupLoaded,
    snapshot.providers,
    snapshot.agents,
    dismissed,
    providersError,
    agentsError,
  ]);

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
        <Wordmark className={styles.heroBrand} />
        <p className={styles.heroKicker}>agentic work, under your control</p>
        <h2>Build, run, and supervise agents from one console.</h2>
        <div className={styles.heroActions}>
          <Button onClick={() => setProjectOpen(true)}>Start a session</Button>
          <Button onClick={() => navigate("/providers")} variant="light">
            Configure providers
          </Button>
        </div>
      </section>

      <div className={styles.setupRow}>
        <HomeChecklist
          progress={progress}
          onOpenStep={(step) => {
            setWizardStep(step);
            setWizardOpen(true);
          }}
        />
      </div>

      <div className={styles.stats}>
        <DashboardCard
          label="Projects"
          value={projectsError ? "—" : projectList.length}
          hint="workspaces"
          icon={<RiFolderLine size={18} />}
        />
        <DashboardCard
          label="Sessions"
          value={sessionsError ? "—" : sessionList.length}
          hint="across all projects"
          icon={<RiChat3Line size={18} />}
        />
        <DashboardCard
          label="Agents"
          value={agentsError ? "—" : agentList.length}
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
            {sessionsError ? (
              <ErrorState
                title="Could not load sessions"
                message={sessionsError.message}
                onRetry={() => void refetchSessions()}
              />
            ) : recentSessions.length === 0 ? (
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
                      <strong>{sessionTitle(session.title)}</strong>
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
            {projectsError ? (
              <ErrorState
                title="Could not load projects"
                message={projectsError.message}
                onRetry={() => void refetchProjects()}
              />
            ) : projectList.length === 0 ? (
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
                    <code>
                      {project.path === "." ? "Project root" : project.path}
                    </code>
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
      <OnboardingWizard
        opened={wizardOpen}
        initialStep={wizardStep}
        onClose={() => {
          dismiss();
          setWizardOpen(false);
        }}
        onDone={(sessionId) => {
          reset();
          setWizardOpen(false);
          navigate(`/sessions/${sessionId}`);
        }}
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



