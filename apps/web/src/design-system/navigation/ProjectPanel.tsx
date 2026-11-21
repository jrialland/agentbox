import {
  RiAddLine,
  RiDeleteBin6Line,
  RiFolderLine,
  RiSettings3Line,
} from "@remixicon/react";
import { useDisclosure } from "@mantine/hooks";
import { modals } from "@mantine/modals";
import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";

import type { Project } from "../../api/endpoints";
import {
  useDeleteProject,
  useDeleteSession,
  useProjects,
  useSessions,
} from "../../api/queries";
import { NewProjectModal } from "../../components/projects/NewProjectModal";
import { NewSessionModal } from "../../components/projects/NewSessionModal";
import { IconButton } from "../icons/IconButton";
import { ConfirmDialog } from "../overlays/ConfirmDialog";
import { EmptyState } from "../primitives/EmptyState";
import { Panel } from "../primitives/Panel";
import styles from "./project-panel.module.css";

export function ProjectPanel() {
  const { data: projects, isLoading, error } = useProjects();
  const { data: sessions } = useSessions();
  const deleteProject = useDeleteProject();
  const deleteSession = useDeleteSession();
  const navigate = useNavigate();
  const location = useLocation();
  const [projectOpen, projectModal] = useDisclosure(false);
  const [editProject, setEditProject] = useState<string | null>(null);
  const [sessionProject, setSessionProject] = useState<string | null>(null);
  const [projectToDelete, setProjectToDelete] = useState<Project | null>(null);

  function onDeleteSession(id: string) {
    modals.openConfirmModal({
      title: "Delete session?",
      labels: { confirm: "Delete", cancel: "Cancel" },
      confirmProps: { color: "red" },
      onConfirm: async () => {
        await deleteSession.mutateAsync(id);
        if (location.pathname === `/sessions/${id}`) navigate("/");
      },
    });
  }

  if (isLoading) return <p className={styles.muted}>Loading.</p>;
  if (error) return <p className={styles.muted}>Failed to load projects</p>;

  const projectList = projects ?? [];

  return (
    <Panel className={styles.panel}>
      <Panel.Header>
        <span>Projects</span>
        <IconButton
          label="New project"
          icon={RiAddLine}
          size={16}
          onClick={projectModal.open}
        />
      </Panel.Header>
      <Panel.Body>
        {projectList.length === 0 ? (
          <EmptyState
            icon={RiFolderLine}
            title="No projects"
            description="Create a project to start a session."
          />
        ) : (
          <ul className={styles.list}>
            {projectList.map((project) => {
              const projectSessions = (sessions ?? [])
                .filter((session) => session.project_id === project.id)
                .sort((a, b) =>
                  (a.created_at ?? "").localeCompare(b.created_at ?? ""),
                );
              return (
                <li key={project.id} className={styles.project}>
                  <div className={styles.projectRow}>
                    <span className={styles.projectName}>{project.name}</span>
                    <div className={styles.actions}>
                      <IconButton
                        label={`Project settings ${project.name}`}
                        icon={RiSettings3Line}
                        size={16}
                        onClick={() => setEditProject(project.id)}
                      />
                      <IconButton
                        label={`New session in ${project.name}`}
                        icon={RiAddLine}
                        size={16}
                        onClick={() => setSessionProject(project.id)}
                      />
                      <IconButton
                        label={`Delete ${project.name}`}
                        icon={RiDeleteBin6Line}
                        size={16}
                        color="red"
                        onClick={() => setProjectToDelete(project)}
                      />
                    </div>
                  </div>
                  <ul className={styles.sessions}>
                    {projectSessions.map((session, index) => (
                      <li key={session.id} className={styles.sessionRow}>
                        <Link to={`/sessions/${session.id}`}>
                          Session {index + 1}
                        </Link>
                        <IconButton
                          label={`Delete session ${session.id}`}
                          icon={RiDeleteBin6Line}
                          size={16}
                          color="red"
                          onClick={() => onDeleteSession(session.id)}
                        />
                      </li>
                    ))}
                  </ul>
                </li>
              );
            })}
          </ul>
        )}
      </Panel.Body>
      <NewProjectModal opened={projectOpen} onClose={projectModal.close} />
      <NewProjectModal
        opened={editProject !== null}
        onClose={() => setEditProject(null)}
        project={
          editProject
            ? projectList.find((project) => project.id === editProject) ?? null
            : null
        }
      />
      <NewSessionModal
        opened={sessionProject !== null}
        onClose={() => setSessionProject(null)}
        projectId={sessionProject ?? ""}
      />
      <ConfirmDialog
        opened={projectToDelete !== null}
        title="Delete project?"
        description={`Delete "${projectToDelete?.name ?? ""}" permanently? This cannot be undone.`}
        requireText={projectToDelete?.name}
        confirmLabel="Delete"
        danger
        onConfirm={async () => {
          if (!projectToDelete) return;
          const onDeletedProjectSession = (sessions ?? []).some(
            (session) =>
              session.project_id === projectToDelete.id &&
              location.pathname === `/sessions/${session.id}`,
          );
          await deleteProject.mutateAsync(projectToDelete.id);
          setProjectToDelete(null);
          if (onDeletedProjectSession) navigate("/");
        }}
        onClose={() => setProjectToDelete(null)}
      />
    </Panel>
  );
}
