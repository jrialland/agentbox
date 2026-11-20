import pathlib
from collections.abc import Callable
from dataclasses import dataclass

from loguru import logger
from pydantic_ai.models import Model as PydanticModel
from sqlmodel import select

from agentbox_harness.spec import AgentSpec
from agentbox_harness.tools.filesystem import FilesystemToolbox
from agentbox_harness.tools.registry import ToolRegistry
from agentbox_harness.tools.web import WebToolbox, WebToolConfig
from agentbox_models.repos.agents import AgentRepository
from agentbox_models.tables.core import (
    Agent,
    Model,
    PlanItem,
    Provider,
    SessionAttachment,
    SessionRow,
    TurnRow,
)
from agentbox_providers.resolver import resolve_model


def web_config_from_settings(settings) -> WebToolConfig:
    return WebToolConfig(
        search_provider=settings.web_search_provider,
        search_timeout=settings.web_search_timeout,
        search_max_results=settings.web_search_max_results,
        search_region=settings.web_search_region,
        search_safesearch=settings.web_search_safesearch,
        ddgs_backend=settings.web_search_ddgs_backend,
        searxng_url=settings.searxng_url,
        fetch_timeout=settings.web_fetch_timeout,
        fetch_max_chars=settings.web_fetch_max_chars,
        fetch_max_bytes=settings.web_fetch_max_bytes,
        user_agent=settings.web_fetch_user_agent,
    )


def build_registry(
    project_root: str,
    extra_read_roots: list[pathlib.Path] | None = None,
    extra_tools: dict[str, Callable] | None = None,
    hooks: list | None = None,
    media_max_dimension: int = 1568,
    media_max_bytes: int = 1_500_000,
    web_config: WebToolConfig | None = None,
    extra_write_roots: list[pathlib.Path] | None = None,
) -> ToolRegistry:
    box = FilesystemToolbox(
        pathlib.Path(project_root),
        extra_read_roots=list(extra_read_roots or []),
        extra_write_roots=list(extra_write_roots or []),
        media_max_dimension=media_max_dimension,
        media_max_bytes=media_max_bytes,
    )
    registry = ToolRegistry(hooks=hooks, root=box.root_dir)
    read_tools = [
        ("read_text_file", box.read_text_file),
        ("read_file", box.read_file),
        ("read_media_file", box.read_media_file),
        ("read_multiple_files", box.read_multiple_files),
        ("list_directory", box.list_directory),
        ("list_directory_with_sizes", box.list_directory_with_sizes),
        ("directory_tree", box.directory_tree),
        ("search_files", box.search_files),
        ("get_file_info", box.get_file_info),
        ("list_allowed_directories", box.list_allowed_directories),
    ]
    web = WebToolbox(web_config)
    read_tools.extend(
        [
            ("web_search", web.web_search),
            ("fetch_url", web.fetch_url),
        ]
    )
    write_tools = [
        ("write_file", box.write_file),
        ("append_file", box.append_file),
        ("edit_file", box.edit_file),
        ("create_directory", box.create_directory),
        ("move_file", box.move_file),
        ("copy_file", box.copy_file),
        ("delete_path", box.delete_path),
    ]
    for name, fn in read_tools:
        registry.register_native(name, fn, required_flags=("read",))
    for name, fn in write_tools:
        registry.register_native(name, fn, required_flags=("write",))
    for name, fn in (extra_tools or {}).items():
        registry.register_native(name, fn)
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
    logger.debug("agent runtime resolved agent={} model={}", agent_name, model.name)
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
        for item in (
            await s.execute(
                select(PlanItem).where(PlanItem.session_id == session_id)
            )
        ).scalars().all():
            await s.delete(item)
        row = (
            await s.execute(select(SessionRow).where(SessionRow.id == session_id))
        ).scalars().first()
        if row is not None:
            await s.delete(row)
        await s.commit()
