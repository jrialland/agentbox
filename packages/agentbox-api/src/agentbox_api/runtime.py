import pathlib
from dataclasses import dataclass

from pydantic_ai.models import Model as PydanticModel
from sqlmodel import select

from agentbox_harness.spec import AgentSpec
from agentbox_harness.tools.filesystem import FilesystemToolbox
from agentbox_harness.tools.registry import ToolRegistry
from agentbox_models.repos.agents import AgentRepository
from agentbox_models.tables.core import (
    Agent,
    Model,
    Provider,
    SessionAttachment,
    SessionRow,
    TurnRow,
)
from agentbox_providers.resolver import resolve_model


def build_registry(project_root: str) -> ToolRegistry:
    box = FilesystemToolbox(pathlib.Path(project_root))
    registry = ToolRegistry()
    registry.register_native("read_text_file", box.read_text_file, required_flags=("read",))
    registry.register_native("write_file", box.write_file, required_flags=("write",))
    registry.register_native("list_directory", box.list_directory, required_flags=("read",))
    return registry


@dataclass
class AgentRuntime:
    agent_id: str
    created_by: str | None
    spec: AgentSpec
    model: PydanticModel


async def resolve_agent_runtime(factory, agent_name: str) -> AgentRuntime:
    async with factory() as s:
        agent = (
            await s.execute(select(Agent).where(Agent.name == agent_name))
        ).scalars().first()
        if agent is None:
            raise KeyError(agent_name)
        model = (
            await s.execute(select(Model).where(Model.id == agent.model_id))
        ).scalars().first()
        provider = (
            await s.execute(select(Provider).where(Provider.id == model.provider_id))
        ).scalars().first()
    spec = await AgentRepository(factory).load(agent_name)
    if spec is None:
        raise KeyError(agent_name)
    return AgentRuntime(
        agent_id=agent.id,
        created_by=agent.created_by,
        spec=spec,
        model=resolve_model(provider, model.name),
    )


async def delete_session_data(factory, session_id: str) -> None:
    """Delete a session's turns, attachments, and row."""
    async with factory() as s:
        for turn in (
            await s.execute(select(TurnRow).where(TurnRow.session_id == session_id))
        ).scalars().all():
            await s.delete(turn)
        for attachment in (
            await s.execute(
                select(SessionAttachment).where(
                    SessionAttachment.session_id == session_id
                )
            )
        ).scalars().all():
            await s.delete(attachment)
        row = (
            await s.execute(select(SessionRow).where(SessionRow.id == session_id))
        ).scalars().first()
        if row is not None:
            await s.delete(row)
        await s.commit()
