import { useState } from "react";

import {
  useAgents,
  useCreateAgent,
  useCreateProject,
  useCreateProvider,
  useCreateSession,
  useModels,
  useProviders,
  useRefreshModels,
} from "../api/queries";
import { FormField } from "../design-system/forms/FormField";
import { Select } from "../design-system/forms/Select";
import { TextInput } from "../design-system/forms/TextInput";
import { Textarea } from "../design-system/forms/Textarea";
import { Modal } from "../design-system/overlays/Modal";
import { Button } from "../design-system/primitives/Button";
import { buildToolBindings } from "../pages/AgentsPage";
import { ProviderForm } from "../pages/providers/ProviderForm";
import {
  EMPTY_PROVIDER_DRAFT,
  type ProviderDraft,
  validateProviderDraft,
} from "../pages/providers/providerPresets";
import styles from "./onboarding.module.css";
import type { OnboardingStep } from "./onboardingProgress";

export const DEFAULT_ONBOARDING_TOOLS = [
  "read_text_file",
  "read_multiple_files",
  "list_directory",
  "search_files",
  "grep",
  "get_file_info",
];

const STEP_ORDER: OnboardingStep[] = [
  "welcome",
  "provider",
  "agent",
  "session",
  "done",
];

const STEP_LABELS: Record<OnboardingStep, string> = {
  welcome: "Welcome",
  provider: "Provider",
  agent: "Agent",
  session: "Session",
  done: "Done",
};

export function OnboardingWizard({
  opened,
  initialStep,
  onClose,
  onDone,
}: {
  opened: boolean;
  initialStep: OnboardingStep;
  onClose: () => void;
  onDone: (sessionId: string) => void;
}) {
  const models = useModels();
  const agents = useAgents();
  const providers = useProviders();
  const createProvider = useCreateProvider();
  const refreshModels = useRefreshModels();
  const createAgent = useCreateAgent();
  const createProject = useCreateProject();
  const createSession = useCreateSession();

  const [step, setStep] = useState<OnboardingStep>(initialStep);
  const [draft, setDraft] = useState<ProviderDraft>(EMPTY_PROVIDER_DRAFT);
  const [providerErrors, setProviderErrors] = useState<
    Partial<Record<keyof ProviderDraft, string>>
  >({});
  const [createdProviderId, setCreatedProviderId] = useState<string | null>(null);
  const [agentName, setAgentName] = useState("");
  const [agentDescription, setAgentDescription] = useState("");
  const [agentInstructions, setAgentInstructions] = useState(
    "You are a helpful coding agent.",
  );
  const [agentModel, setAgentModel] = useState<string | null>(null);
  const [agentTools, setAgentTools] = useState<string[]>(
    DEFAULT_ONBOARDING_TOOLS,
  );
  const [createdAgent, setCreatedAgent] = useState<string | null>(null);
  const [projectName, setProjectName] = useState("My project");
  const [projectPath, setProjectPath] = useState(".");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const createdProvider = providers.data?.find(
    (provider) => provider.id === createdProviderId,
  );
  const modelOptions = (models.data ?? []).map((model) => ({
    value: model.name,
    label: model.name,
  }));
  const agentOptions = (agents.data ?? []).map((agent) => ({
    value: agent.name,
    label: agent.name,
  }));

  async function createProviderStep() {
    setError(null);
    const nextErrors = validateProviderDraft(draft);
    setProviderErrors(nextErrors);
    if (Object.keys(nextErrors).length > 0) {
      setError("Fix the highlighted provider fields.");
      return;
    }
    try {
      const provider = await createProvider.mutateAsync({
        name: draft.name,
        kind: draft.kind,
        base_url: draft.baseUrl || undefined,
        api_key: draft.apiKey || undefined,
        models_url: draft.modelsUrl || undefined,
      });
      setCreatedProviderId(provider.id);
      await refreshModels.mutateAsync(provider.id);
      setStep("agent");
    } catch {
      setError("Could not create the provider. Check the fields and try again.");
    }
  }

  async function createAgentStep() {
    setError(null);
    if (!agentName.trim() || !agentModel) {
      setError("Enter an agent name and choose a model.");
      return;
    }
    try {
      const agent = await createAgent.mutateAsync({
        name: agentName,
        description: agentDescription,
        instructions: agentInstructions,
        model: agentModel,
        tool_bindings: buildToolBindings(agentTools),
        mode_definitions: [
          { name: "ask", flags: { write: false } },
          { name: "agent", flags: { write: true } },
        ],
      });
      setCreatedAgent(agent.name);
      setStep("session");
    } catch {
      setError("Could not create the agent. Check the model and try again.");
    }
  }

  async function createSessionStep() {
    setError(null);
    if (!projectName.trim() || !projectPath.trim()) {
      setError("Enter a project name and path.");
      return;
    }
    try {
      const project = await createProject.mutateAsync({
        name: projectName,
        path: projectPath,
        extra_roots: [],
      });
      const session = await createSession.mutateAsync({
        project_id: project.id,
        agent_id: createdAgent ?? agentName,
      });
      setSessionId(session.id);
      onDone(session.id);
    } catch {
      setError("Could not create the project or session.");
    }
  }

  function close() {
    setStep("welcome");
    setError(null);
    onClose();
  }

  return (
    <Modal
      opened={opened}
      onClose={close}
      title="Set up Agentbox"
      size="lg"
      closeOnClickOutside={false}
    >
      <div className={styles.wizard}>
        <div className={styles.steps}>
          {STEP_ORDER.map((id, index) => (
            <span
              key={id}
              className={id === step ? styles.stepActive : styles.step}
              data-testid={`wizard-step-${id}`}
              aria-current={id === step ? "step" : undefined}
            >
              {STEP_LABELS[id]}
              {index < STEP_ORDER.length - 1 && (
                <span className={styles.stepSep} aria-hidden="true">
                  ›
                </span>
              )}
            </span>
          ))}
        </div>

        {step === "welcome" && (
          <div>
            <h2>Connect your first provider</h2>
            <p>
              Agentbox needs one model endpoint before it can create an agent and
              start a session. You can skip this and configure it later.
            </p>
            <Button onClick={() => setStep("provider")}>Get started</Button>
          </div>
        )}

        {step === "provider" && (
          <div>
            <h2>Provider</h2>
            <ProviderForm
              value={draft}
              onChange={setDraft}
              providerId={createdProviderId ?? undefined}
              errors={providerErrors}
              onSubmit={createProviderStep}
            />
            {createdProvider && (
              <p style={{ color: "var(--ab-text-muted)" }}>
                Using {createdProvider.name}
              </p>
            )}
            <Button
              onClick={createProviderStep}
              loading={createProvider.isPending || refreshModels.isPending}
            >
              Create provider
            </Button>
          </div>
        )}

        {step === "agent" && (
          <div style={{ display: "grid", gap: 8 }}>
            <h2>Agent</h2>
            <FormField label="Agent name" required>
              <TextInput
                value={agentName}
                onChange={(event) => setAgentName(event.currentTarget.value)}
              />
            </FormField>
            <FormField label="Description">
              <TextInput
                value={agentDescription}
                onChange={(event) => setAgentDescription(event.currentTarget.value)}
              />
            </FormField>
            <FormField label="Instructions">
              <Textarea
                minRows={3}
                value={agentInstructions}
                onChange={(event) => setAgentInstructions(event.currentTarget.value)}
              />
            </FormField>
            <FormField label="Model" required>
              <Select data={modelOptions} value={agentModel} onChange={setAgentModel} searchable />
            </FormField>
            <p style={{ color: "var(--ab-text-muted)", margin: 0 }}>
              The first-run agent starts with read-only filesystem tools. You can
              add write tools later.
            </p>
            <Button onClick={createAgentStep} loading={createAgent.isPending}>
              Create agent
            </Button>
          </div>
        )}

        {step === "session" && (
          <div style={{ display: "grid", gap: 8 }}>
            <h2>Project and session</h2>
            <FormField label="Project name" required>
              <TextInput
                value={projectName}
                onChange={(event) => setProjectName(event.currentTarget.value)}
              />
            </FormField>
            <FormField label="Project path" required>
              <TextInput
                value={projectPath}
                onChange={(event) => setProjectPath(event.currentTarget.value)}
              />
            </FormField>
            <FormField label="Agent" required>
              <Select
                data={agentOptions}
                value={createdAgent ?? agentName}
                onChange={(value) => setCreatedAgent(value)}
              />
            </FormField>
            <Button
              onClick={createSessionStep}
              loading={createProject.isPending || createSession.isPending}
            >
              Create project and start session
            </Button>
          </div>
        )}

        {step === "done" && (
          <div>
            <h2>Setup complete</h2>
            <p>Your provider, agent, project, and first session are ready.</p>
            <Button
              onClick={() => {
                if (sessionId) onDone(sessionId);
                onClose();
              }}
            >
              Open Home
            </Button>
          </div>
        )}

        {error && (
          <p className={styles.error} role="alert">
            {error}
          </p>
        )}

        <div className={styles.actions}>
          {step !== "welcome" && step !== "done" && (
            <Button
              variant="light"
              onClick={() =>
                setStep(
                  step === "provider"
                    ? "welcome"
                    : step === "agent"
                      ? "provider"
                      : "agent",
                )
              }
            >
              Back
            </Button>
          )}
          {step !== "done" && (
            <Button variant="subtle" onClick={close}>
              Skip setup
            </Button>
          )}
        </div>
      </div>
    </Modal>
  );
}
