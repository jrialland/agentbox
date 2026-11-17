import uuid

from agentbox_harness.agent_factory import build_agent
from agentbox_harness.errors import RunOutcome
from agentbox_harness.events import EventBus
from agentbox_harness.messages import turns_to_messages
from agentbox_harness.run import Run, RunManager
from agentbox_harness.session import Session, Turn
from agentbox_harness.spec import AgentSpec
from agentbox_harness.tools.registry import ToolRegistry


class Harness:
    def __init__(
        self,
        registry: ToolRegistry,
        model: str,
        store_factory,
        sub_agents: dict[str, AgentSpec] | None = None,
    ):
        self.registry = registry
        self.model = model
        self.store_factory = store_factory
        self.sub_agents = sub_agents or {}
        self.run_manager = RunManager(model=model)

    def start_session(
        self,
        spec: AgentSpec,
        project_root: str,
        mode_name: str,
    ) -> Session:
        store = self.store_factory()
        session = Session(
            session_id=uuid.uuid4().hex,
            project_root=project_root,
            agent_spec=spec,
            store=store,
            head_id=None,
        )
        session._mode_name = mode_name
        return session

    def _resolve_mode(self, session: Session):
        name = getattr(session, "_mode_name", "agent")
        for mode in session.agent_spec.mode_definitions:
            if mode.name == name:
                return mode
        raise ValueError(f"Unknown mode: {name}")

    def run(
        self,
        session: Session,
        user_message: str,
        bus: EventBus,
        model_override=None,
    ) -> Run:
        message_history = turns_to_messages(session.history())

        turn = Turn(
            id=uuid.uuid4().hex,
            role="user",
            content=user_message,
            parent_id=session.head_id,
        )
        session.append(turn, parent_id=session.head_id)

        mode = self._resolve_mode(session)
        agent = build_agent(
            session.agent_spec,
            mode,
            self.registry,
            self.model,
            sub_agents=self.sub_agents,
        )
        return self.run_manager.start(
            agent,
            user_message,
            run_id=uuid.uuid4().hex,
            bus=bus,
            model_override=model_override,
            message_history=message_history,
        )

    async def run_turn(
        self,
        session: Session,
        user_message: str,
        bus: EventBus,
        model_override=None,
    ) -> RunOutcome:
        run = self.run(session, user_message, bus, model_override)
        outcome = await run.await_outcome()
        if outcome.status == "success":
            result = await run.await_result()
            turn = Turn(
                id=uuid.uuid4().hex,
                role="assistant",
                content=str(result.output),
                parent_id=session.head_id,
            )
            session.append(turn, parent_id=session.head_id)
        return outcome
