"""Orchestrate session runs: build the agent, prepare tools, and drive runs.

:class:`Harness` owns the run manager and middleware pipeline. It starts
sessions from an Agent configuration, prepares MCP toolsets, launches runs as
background tasks, and records assistant turns for completed runs.
"""

import uuid

from loguru import logger
from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.models import Model

from agentbox_harness.agent_factory import build_agent
from agentbox_harness.compaction import CompactionConfig, CompactionMiddleware
from agentbox_harness.context_editing import ContextEditingConfig
from agentbox_harness.errors import RunOutcome
from agentbox_harness.events import EventBus
from agentbox_harness.messages import turns_to_messages
from agentbox_harness.middleware import (
    MiddlewarePipeline,
    RunContext,
    RunMiddleware,
    SessionReminder,
)
from agentbox_harness.run import Run, RunManager
from agentbox_harness.session import Session, Turn
from agentbox_harness.spec import AgentSpec, McpToolBinding, Mode
from agentbox_harness.tools.mcp_session import (
    McpSessionManager,
    SessionToolsets,
    get_mcp_session_manager,
)
from agentbox_harness.tools.registry import ToolRegistry
from agentbox_harness.usage import context_tokens_from_usage


class Harness:
    """Coordinator for session lifecycle, agent construction, and runs."""

    def __init__(
        self,
        registry: ToolRegistry,
        model: Model,
        store_factory,
        middleware: list[RunMiddleware] | None = None,
        compaction: CompactionConfig | None = None,
        subagent_session_runner=None,
        mcp_manager: McpSessionManager | None = None,
        reminders: list[SessionReminder] | None = None,
        context_editing: ContextEditingConfig | None = None,
        plugin_hooks: AbstractCapability | None = None,
    ):
        self.registry = registry
        self.model = model
        self.store_factory = store_factory
        self.run_manager = RunManager()
        self.middleware = MiddlewarePipeline(
            middleware
            if middleware is not None
            else [CompactionMiddleware(compaction)]
        )
        self.subagent_session_runner = subagent_session_runner
        self.mcp_manager = mcp_manager or get_mcp_session_manager()
        self.reminders = list(reminders or [])
        self.context_editing = context_editing
        self.plugin_hooks = plugin_hooks

    async def prepare_mcp(self, session: Session) -> SessionToolsets:
        """Open the MCP toolsets required by a session's Agent configuration.

        Args:
            session: Session whose bindings and project roots define the
                toolsets.

        Returns:
            MCP toolsets for the session, managed by the MCP session manager.
        """
        spec = session.agent_spec
        bindings = (
            [b for b in spec.tool_bindings if isinstance(b, McpToolBinding)]
            if spec is not None
            else []
        )
        return await self.mcp_manager.toolsets_for(
            session.session_id,
            bindings,
            session.project_root,
            [*session.extra_roots, *session.plugin_roots],
        )

    def start_session(
        self,
        spec: AgentSpec,
        project_root: str,
        mode_name: str,
    ) -> Session:
        """Create a new session for an Agent configuration.

        Args:
            spec: Agent configuration the session runs.
            project_root: Project root the session is scoped to.
            mode_name: Name of the mode the session starts in.

        Returns:
            A new in-memory session with no history.
        """
        store = self.store_factory()
        return Session(
            session_id=uuid.uuid4().hex,
            project_root=project_root,
            agent_spec=spec,
            store=store,
            head_id=None,
            mode_name=mode_name,
        )

    def _resolve_mode(self, session: Session):
        """Resolve the session's mode from its Agent configuration.

        Configurations without mode definitions fall back to a permissive mode.

        Raises:
            ValueError: If the session has no Agent configuration, or the mode
                name is unknown when definitions exist.
        """
        spec = session.agent_spec
        if spec is None:
            raise ValueError("Session has no agent spec")
        if not spec.mode_definitions:
            return Mode(name=session.mode_name, flags={"write": True})
        for mode in spec.mode_definitions:
            if mode.name == session.mode_name:
                return mode
        raise ValueError(f"Unknown mode: {session.mode_name}")

    async def run(
        self,
        session: Session,
        user_message: str,
        bus: EventBus,
        model_override=None,
        prompt_override=None,
        record_user_turn: bool = True,
        user_attachments: list[dict] | None = None,
    ) -> Run:
        """Launch an asynchronous run for one user message.

        Prepares middleware, records the user turn, gathers reminders, resolves
        the mode, opens MCP toolsets, builds the agent, and starts a managed
        task that streams events onto the bus.

        Args:
            session: Session the run belongs to.
            user_message: User prompt for this run.
            bus: Event bus receiving run events.
            model_override: Model override passed to the run manager.
            prompt_override: Structured prompt parts replacing the plain
                prompt.
            record_user_turn: Whether to append the user message as a turn.
            user_attachments: Attachments recorded with the user turn.

        Returns:
            The started run, whose task is already scheduled.

        Raises:
            ValueError: If the session has no Agent configuration or requests
                an unknown mode.
        """
        model = model_override or self.model
        context = RunContext(
            session=session,
            model=model,
            bus=bus,
            prompt=user_message,
            prompt_override=prompt_override,
        )
        await self.middleware.prepare(context)

        # Record the user turn before building history so the run sees it.
        if record_user_turn:
            turn = Turn(
                id=uuid.uuid4().hex,
                role="user",
                content=user_message,
                parent_id=session.head_id,
                attachments=user_attachments,
            )
            await session.append(turn, parent_id=session.head_id)
        message_history = turns_to_messages(await session.history())

        reminder_texts: list[str] = []
        for provider in self.reminders:
            try:
                text = await provider.reminder(session)
            except Exception:
                # A failing reminder provider must not block the run.
                logger.exception("reminder provider failed")
                continue
            if text:
                reminder_texts.append(text)
        reminder = "\n\n".join(reminder_texts)
        effective_prompt = (
            user_message if not reminder else f"{user_message}\n\n{reminder}"
        )
        effective_override = prompt_override
        if prompt_override is not None and reminder:
            effective_override = [*prompt_override, reminder]

        mode = self._resolve_mode(session)
        spec = session.agent_spec
        if spec is None:
            raise ValueError("Session has no agent spec")
        logger.debug(
            "harness run start agent={} mode={} session={}",
            spec.name,
            mode.name,
            session.session_id,
        )
        session_tools = await self.prepare_mcp(session)
        agent = build_agent(
            spec,
            mode,
            self.registry,
            self.model,
            subagent_session_runner=self.subagent_session_runner,
            session_id=session.session_id,
            stdio_toolsets=session_tools.toolsets,
            context_editing=self.context_editing,
            plugin_hooks=self.plugin_hooks,
        )
        # The run manager owns the background task, cancellation token, and
        # overflow recovery callback for this run.
        return self.run_manager.start(
            agent,
            effective_prompt,
            run_id=uuid.uuid4().hex,
            bus=bus,
            model_override=model_override,
            message_history=message_history,
            prompt_override=effective_override,
            on_context_overflow=lambda: self.middleware.recover(context),
        )

    async def run_turn(
        self,
        session: Session,
        user_message: str,
        bus: EventBus,
        model_override=None,
    ) -> RunOutcome:
        """Run one turn to completion and record the assistant reply.

        Delegates to :meth:`run`, waits for the outcome, and on success appends
        the assistant output as a turn with its reported context usage.

        Args:
            session: Session the turn belongs to.
            user_message: User prompt for the turn.
            bus: Event bus receiving run events.
            model_override: Model override passed to the run manager.

        Returns:
            The terminal outcome of the run.

        Raises:
            ValueError: If the session has no Agent configuration or requests
                an unknown mode.
        """
        run = await self.run(session, user_message, bus, model_override)
        outcome = await run.await_outcome()
        if outcome.status == "success":
            result = await run.await_result()
            context_tokens = context_tokens_from_usage(result.response.usage)
            turn = Turn(
                id=uuid.uuid4().hex,
                role="assistant",
                content=str(result.output),
                parent_id=session.head_id,
                context_tokens=context_tokens,
            )
            await session.append(turn, parent_id=session.head_id)
        return outcome
