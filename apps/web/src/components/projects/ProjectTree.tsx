import { Button } from "@mantine/core";
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
import { NewProjectModal } from "./NewProjectModal";
import { NewSessionModal } from "./NewSessionModal";

export function ProjectTree() {
  const { data: projects, isLoading, error } = useProjects();
  const { data: sessions } = useSessions();
  const del = useDeleteProject();
  const deleteSession = useDeleteSession();
  const navigate = useNavigate();
  const location = useLocation();
  const [projectOpen, projectModal] = useDisclosure(false);
  const [editProject, setEditProject] = useState<Project | null>(null);
  const [sessionProject, setSessionProject] = useState<string | null>(null);

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

  if (isLoading) return <p className="menu-label">Loading…</p>;
  if (error) return <p className="menu-label">Failed to load projects</p>;

  return (
    <div>
      <Button size="xs" mb="sm" onClick={projectModal.open}>
        New project
      </Button>
      <ul className="menu-list">
        {(projects ?? []).map((p) => {
          const projectSessions = (sessions ?? [])
            .filter((s) => s.project_id === p.id)
            .sort((a, b) => (a.created_at ?? "").localeCompare(b.created_at ?? ""));
          return (
            <li key={p.id}>
              <div className="is-flex is-justify-content-space-between">
                <span>{p.name}</span>
                <span>
                  <button
                    type="button"
                    aria-label={`Project settings ${p.name}`}
                    onClick={() => setEditProject(p)}
                  >
                    Edit
                  </button>
                  <button
                    type="button"
                    aria-label={`New session in ${p.name}`}
                    onClick={() => setSessionProject(p.id)}
                  >
                    +
                  </button>
                  <button
                    type="button"
                    aria-label={`Delete ${p.name}`}
                    onClick={() => del.mutate(p.id)}
                  >
                    ×
                  </button>
                </span>
              </div>
              <ul>
                {projectSessions.map((s, i) => (
                  <li
                    key={s.id}
                    className="is-flex is-justify-content-space-between"
                  >
                    <Link to={`/sessions/${s.id}`}>Session {i + 1}</Link>
                    <button
                      type="button"
                      aria-label={`Delete session ${s.id}`}
                      onClick={() => onDeleteSession(s.id)}
                    >
                      ×
                    </button>
                  </li>
                ))}
              </ul>
            </li>
          );
        })}
      </ul>
      <NewProjectModal opened={projectOpen} onClose={projectModal.close} />
      <NewProjectModal
        opened={editProject !== null}
        onClose={() => setEditProject(null)}
        project={editProject}
      />
      <NewSessionModal
        opened={sessionProject !== null}
        onClose={() => setSessionProject(null)}
        projectId={sessionProject ?? ""}
      />
    </div>
  );
}
