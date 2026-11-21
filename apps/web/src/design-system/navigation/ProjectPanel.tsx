import {
  RiAddLine,
  RiDeleteBin6Line,
  RiFolderLine,
  RiPencilLine,
  RiSettings3Line,
} from "@remixicon/react";
import { TextInput } from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import { notifications } from "@mantine/notifications";
import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";

import type { Project } from "../../api/endpoints";
import { sessionTitle } from "../../lib/sessionTitle";
import {
  useDeleteProject,
  useDeleteSession,
  useProjects,
  useRenameSession,
  useSessions,
} from "../../api/queries";
import { NewProjectModal } from "../../components/projects/NewProjectModal";
import { NewSessionModal } from "../../components/projects/NewSessionModal";
import { IconButton } from "../icons/IconButton";
import { ConfirmDialog } from "../overlays/ConfirmDialog";
import { ErrorState } from "../patterns/ErrorState";
import { EmptyState } from "../primitives/EmptyState";
import { Panel } from "../primitives/Panel";
import styles from "./project-panel.module.css";

export function ProjectPanel() {
  const { data: projects, isLoading, error, refetch } = useProjects();
  const { data: sessions } = useSessions();
  const deleteProject = useDeleteProject();
  const deleteSession = useDeleteSession();
  const renameSession = useRenameSession();
  const navigate = useNavigate();
  const location = useLocation();
  const [projectOpen, projectModal] = useDisclosure(false);
  const [editProject, setEditProject] = useState<string | null>(null);
  const [sessionProject, setSessionProject] = useState<string | null>(null);
  const [projectToDelete, setProjectToDelete] = useState<Project | null>(null);
  const [sessionToDelete, setSessionToDelete] = useState<string | null>(null);
  const [renaming, setRenaming] = useState<string | null>(null);
  const [titleDraft, setTitleDraft] = useState("");

  async function saveTitle(sessionId: string) {
    const title = titleDraft.trim();
    if (!title || renameSession.isPending) return;
    try {
      await renameSession.mutateAsync({ sid: sessionId, title });
      setRenaming(null);
    } catch {
      notifications.show({ message: "Failed to rename session", color: "red" });
    }
  }

  if (isLoading) return <p className={styles.muted}>Loading.</p>;
  if (error) {
    return (
      <ErrorState
        title="Could not load projects"
        message={error.message}
        onRetry={() => void refetch()}
      />
    );
  }

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
                    {projectSessions.map((session) => (
                      <li key={session.id} className={styles.sessionRow}>
                        {renaming === session.id ? (
                          <TextInput
                            aria-label="Session title"
                            className={styles.titleInput}
                            maxLength={120}
                            value={titleDraft}
                            onChange={(event) =>
                              setTitleDraft(event.currentTarget.value)
                            }
                            onKeyDown={(event) => {
                              if (event.key === "Enter") {
                                void saveTitle(session.id);
                              }
                              if (event.key === "Escape") setRenaming(null);
                            }}
                            autoFocus
                          />
                        ) : (
                          <Link to={`/sessions/${session.id}`}>
                            <span className={styles.sessionTitle}>
                              {sessionTitle(session.title)}
                            </span>
                          </Link>
                        )}
                        <div className={styles.actions}>
                          <IconButton
                            label={`Rename session ${session.id}`}
                            icon={RiPencilLine}
                            size={16}
                            onClick={() => {
                              setTitleDraft(session.title ?? "");
                              setRenaming(session.id);
                            }}
                          />
                          <IconButton
                            label={`Delete session ${session.id}`}
                            icon={RiDeleteBin6Line}
                            size={16}
                            color="red"
                            onClick={() => setSessionToDelete(session.id)}
                          />
                        </div>
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
      <ConfirmDialog
        opened={sessionToDelete !== null}
        title="Delete session?"
        description="Delete this session permanently? This cannot be undone."
        confirmLabel="Delete"
        danger
        onConfirm={async () => {
          if (!sessionToDelete) return;
          await deleteSession.mutateAsync(sessionToDelete);
          setSessionToDelete(null);
          if (location.pathname === `/sessions/${sessionToDelete}`) {
            navigate("/");
          }
        }}
        onClose={() => setSessionToDelete(null)}
      />
    </Panel>
  );
}
