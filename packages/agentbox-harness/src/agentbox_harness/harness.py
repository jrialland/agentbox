import uuid

from loguru import logger
from pydantic_ai.models import Model

from agentbox_harness.agent_factory import build_agent
from agentbox_harness.compaction import CompactionConfig, CompactionMiddleware
from agentbox_harness.errors import RunOutcome
from agentbox_harness.events import EventBus
from agentbox_harness.messages import turns_to_messages
from agentbox_harness.middleware import MiddlewarePipeline, RunContext, RunMiddleware
from agentbox_harness.run import Run, RunManager
from agentbox_harness.session import Session, Turn
from agentbox_harness.spec import AgentSpec
from agentbox_harness.tools.registry import ToolRegistry
from agentbox_harness.usage import context_tokens_from_usage


class Harness:
    def __init__(
        self,
        registry: ToolRegistry,
        model: Model,
        store_factory,
        sub_agents: dict[str, AgentSpec] | None = None,
        middleware: list[RunMiddleware] | None = None,
        compaction: CompactionConfig | None = None,
        sub_session_runner=None,
    ):
        self.registry = registry
        self.model = model
        self.store_factory = store_factory
        self.sub_agents = sub_agents or {}
        self.run_manager = RunManager()
        self.middleware = MiddlewarePipeline(
            middleware
            if middleware is not None
            else [CompactionMiddleware(compaction)]
        )
        self.sub_session_runner = sub_session_runner

    def start_session(
        self,
        spec: AgentSpec,
        project_root: str,
        mode_name: str,
    ) -> Session:
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
        spec = session.agent_spec
        if spec is None:
            raise ValueError("Session has no agent spec")
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
    ) -> Run:
        model = model_override or self.model
        context = RunContext(
            session=session,
            model=model,
            bus=bus,
            prompt=user_message,
            prompt_override=prompt_override,
        )
        await self.middleware.prepare(context)

        turn = Turn(
            id=uuid.uuid4().hex,
            role="user",
            content=user_message,
            parent_id=session.head_id,
        )
        await session.append(turn, parent_id=session.head_id)
        message_history = turns_to_messages(await session.history())

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
        agent = build_agent(
            spec,
            mode,
            self.registry,
            self.model,
            sub_agents=self.sub_agents,
            sub_session_runner=self.sub_session_runner,
            session_id=session.session_id,
        )
        return self.run_manager.start(
            agent,
            user_message,
            run_id=uuid.uuid4().hex,
            bus=bus,
            model_override=model_override,
            message_history=message_history,
            prompt_override=prompt_override,
            on_context_overflow=lambda: self.middleware.recover(context),
        )

    async def run_turn(
        self,
        session: Session,
        user_message: str,
        bus: EventBus,
        model_override=None,
    ) -> RunOutcome:
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
