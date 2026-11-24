"""Persist agent configurations and their tool, plugin, and mode bindings.

An agent configuration is stored as one ``Agent`` row plus child binding and
mode rows. ``AgentRepository`` owns its transactions: each public method opens a
session from the injected factory and commits its own writes. The private
binding helpers instead operate on a caller-owned session so a save or load
stays within a single transaction.
"""

import uuid

from loguru import logger
from sqlalchemy import delete
from sqlmodel import select

from agentbox_harness.spec import (
    AgentSpec,
    McpToolBinding,
    Mode,
    ModelBinding,
    NativeToolBinding,
    PluginMcpBinding,
)
from agentbox_models.repos.model_labels import (
    canonical_label,
    resolve_model_label,
)
from agentbox_models.tables.core import (
    Agent,
    AgentMode,
    AgentModeFlag,
    AgentPluginMcpBinding,
    AgentToolBinding,
    AgentToolBindingArg,
    AgentToolBindingEnv,
    AgentToolBindingEnvPassthrough,
    AgentToolBindingRequiredFlag,
    Model,
    Provider,
)


async def _save_bindings(session, agent_id: str, bindings) -> None:
    await session.execute(
        delete(AgentToolBinding).where(AgentToolBinding.agent_id == agent_id)  # ty: ignore[invalid-argument-type]
    )
    for position, binding in enumerate(bindings):
        binding_id = uuid.uuid4().hex
        if isinstance(binding, NativeToolBinding):
            session.add(
                AgentToolBinding(
                    id=binding_id,
                    agent_id=agent_id,
                    position=position,
                    kind="native",
                    name=binding.name,
                )
            )
            for flag in dict.fromkeys(binding.required_flags):
                session.add(
                    AgentToolBindingRequiredFlag(binding_id=binding_id, flag=flag)
                )
            continue

        session.add(
            AgentToolBinding(
                id=binding_id,
                agent_id=agent_id,
                position=position,
                kind="mcp",
                server_url=binding.server_url or None,
                tool_prefix=binding.tool_prefix or None,
                server_id=binding.id or None,
                command=binding.command or None,
                cwd=binding.cwd or None,
            )
        )
        for index, value in enumerate(binding.args):
            session.add(
                AgentToolBindingArg(binding_id=binding_id, position=index, value=value)
            )
        for key, value in binding.env.items():
            session.add(
                AgentToolBindingEnv(binding_id=binding_id, key=key, value=value)
            )
        for index, name in enumerate(binding.env_passthrough):
            session.add(
                AgentToolBindingEnvPassthrough(
                    binding_id=binding_id, position=index, name=name
                )
            )


async def _load_bindings(session, agent_id: str):
    rows = (
        await session.execute(
            select(AgentToolBinding)
            .where(AgentToolBinding.agent_id == agent_id)
            .order_by(AgentToolBinding.position)  # ty: ignore[invalid-argument-type]
        )
    ).scalars().all()
    bindings = []
    for row in rows:
        if row.kind == "native":
            flags = (
                await session.execute(
                    select(AgentToolBindingRequiredFlag.flag)
                    .where(AgentToolBindingRequiredFlag.binding_id == row.id)
                    .order_by(AgentToolBindingRequiredFlag.flag)
                )
            ).scalars().all()
            bindings.append(
                NativeToolBinding(name=row.name or "", required_flags=tuple(flags))
            )
            continue

        args = (
            await session.execute(
                select(AgentToolBindingArg.value)
                .where(AgentToolBindingArg.binding_id == row.id)
                .order_by(AgentToolBindingArg.position)  # ty: ignore[invalid-argument-type]
            )
        ).scalars().all()
        env_rows = (
            await session.execute(
                select(AgentToolBindingEnv).where(
                    AgentToolBindingEnv.binding_id == row.id
                )
            )
        ).scalars().all()
        passthrough = (
            await session.execute(
                select(AgentToolBindingEnvPassthrough.name)
                .where(AgentToolBindingEnvPassthrough.binding_id == row.id)
                .order_by(AgentToolBindingEnvPassthrough.position)  # ty: ignore[invalid-argument-type]
            )
        ).scalars().all()
        bindings.append(
            McpToolBinding(
                server_url=row.server_url or "",
                tool_prefix=row.tool_prefix or "",
                id=row.server_id or "",
                command=row.command or "",
                args=list(args),
                env={item.key: item.value for item in env_rows},
                env_passthrough=list(passthrough),
                cwd=row.cwd or "",
            )
        )
    return bindings


async def _save_plugin_bindings(session, agent_id: str, bindings) -> None:
    await session.execute(
        delete(AgentPluginMcpBinding).where(
            AgentPluginMcpBinding.agent_id == agent_id  # ty: ignore[invalid-argument-type]
        )
    )
    for position, binding in enumerate(bindings):
        session.add(
            AgentPluginMcpBinding(
                id=uuid.uuid4().hex,
                agent_id=agent_id,
                position=position,
                plugin=binding.plugin,
                server=binding.server,
                project_id=binding.project_id,
                binding_id=binding.id,
            )
        )


async def _load_plugin_bindings(session, agent_id: str):
    rows = (
        await session.execute(
            select(AgentPluginMcpBinding)
            .where(AgentPluginMcpBinding.agent_id == agent_id)
            .order_by(AgentPluginMcpBinding.position)  # ty: ignore[invalid-argument-type]
        )
    ).scalars().all()
    return [
        PluginMcpBinding(
            plugin=row.plugin,
            server=row.server,
            project_id=row.project_id,
            id=row.binding_id,
        )
        for row in rows
    ]


async def _save_modes(session, agent_id: str, modes) -> None:
    await session.execute(delete(AgentMode).where(AgentMode.agent_id == agent_id))  # ty: ignore[invalid-argument-type]
    for position, mode in enumerate(modes):
        mode_id = uuid.uuid4().hex
        session.add(
            AgentMode(
                id=mode_id,
                agent_id=agent_id,
                position=position,
                name=mode.name,
            )
        )
        for flag, enabled in mode.flags.items():
            session.add(
                AgentModeFlag(mode_id=mode_id, name=flag, enabled=bool(enabled))
            )


async def _load_modes(session, agent_id: str) -> list[Mode]:
    rows = (
        await session.execute(
            select(AgentMode)
            .where(AgentMode.agent_id == agent_id)
            .order_by(AgentMode.position)  # ty: ignore[invalid-argument-type]
        )
    ).scalars().all()
    modes = []
    for row in rows:
        flags = (
            await session.execute(
                select(AgentModeFlag).where(AgentModeFlag.mode_id == row.id)
            )
        ).scalars().all()
        modes.append(
            Mode(name=row.name, flags={flag.name: flag.enabled for flag in flags})
        )
    return modes


class AgentRepository:
    """Load and persist agent configurations and their binding rows.

    Instances are bound to a session factory. Each public method opens a short
    session, commits its own writes, and never leaves a transaction open for the
    caller.
    """

    def __init__(self, session_factory):
        self._factory = session_factory

    async def save(self, spec: AgentSpec) -> AgentSpec:
        """Insert or update an agent configuration by name.

        Resolves the model from ``spec.model_label`` when present, otherwise from
        ``spec.model_binding.model``. An existing row with the same name is
        updated in place, and its tool, plugin, and mode bindings are replaced
        wholesale.

        Args:
            spec: Agent configuration to persist.

        Returns:
            A copy of ``spec`` with the resolved model binding and canonical label.

        Raises:
            ValueError: If the label or model name does not resolve to a model.
        """
        async with self._factory() as s:
            label = canonical_label(spec.model_label) if spec.model_label else None
            if label:
                model = await resolve_model_label(s, label)
                if model is None:
                    raise ValueError(f"No model for label: {label}")
            else:
                model = (
                    await s.execute(
                        select(Model).where(Model.name == spec.model_binding.model)
                    )
                ).scalars().first()
                if model is None:
                    raise ValueError(f"Unknown model: {spec.model_binding.model}")
            provider = (
                await s.execute(
                    select(Provider).where(Provider.id == model.provider_id)
                )
            ).scalars().first()

            existing = (
                await s.execute(select(Agent).where(Agent.name == spec.name))
            ).scalars().first()
            row = existing or Agent(
                id=uuid.uuid4().hex,
                name=spec.name,
                description="",
                instructions="",
                model_id=model.id,
            )
            row.description = spec.description
            row.instructions = spec.instructions
            row.model_id = model.id
            row.model_label = label
            s.add(row)
            # Flush first so a newly created agent row has an id before the
            # child binding and mode rows reference it. The commit below closes
            # the transaction after every child row is written.
            await s.flush()
            await _save_bindings(s, row.id, spec.tool_bindings)
            await _save_plugin_bindings(
                s, row.id, spec.plugin_mcp_bindings
            )
            await _save_modes(s, row.id, spec.mode_definitions)
            await s.commit()
            logger.info("agent saved name={}", spec.name)
        return spec.model_copy(
            update={
                "model_binding": ModelBinding(
                    model=model.name, provider=provider.name
                ),
                "model_label": label,
            }
        )

    async def load(self, name: str) -> AgentSpec | None:
        """Load an agent configuration by name.

        Prefers the row's model label when set and otherwise falls back to the
        stored model id. Bindings and modes are reconstructed in their persisted
        order.

        Args:
            name: Agent configuration name.

        Returns:
            The reconstructed spec, or ``None`` when no row matches.

        Raises:
            ValueError: If the row references a model that cannot be resolved.
        """
        async with self._factory() as s:
            row = (
                await s.execute(select(Agent).where(Agent.name == name))
            ).scalars().first()
            if row is None:
                return None
            model = None
            if row.model_label:
                model = await resolve_model_label(s, row.model_label)
            if model is None:
                model = (
                    await s.execute(select(Model).where(Model.id == row.model_id))
                ).scalars().first()
            if model is None:
                raise ValueError(f"Unknown model for agent: {name}")
            provider = (
                await s.execute(
                    select(Provider).where(Provider.id == model.provider_id)
                )
            ).scalars().first()
            return AgentSpec(
                name=row.name,
                description=row.description,
                instructions=row.instructions,
                tool_bindings=await _load_bindings(s, row.id),
                plugin_mcp_bindings=await _load_plugin_bindings(s, row.id),
                mode_definitions=await _load_modes(s, row.id),
                model_binding=ModelBinding(
                    model=model.name, provider=provider.name
                ),
                model_label=row.model_label,
            )

    async def list(self) -> list[AgentSpec]:
        """Return every agent configuration.

        Each row is reloaded through :meth:`load`. Listing raises ``ValueError``
        when an entry's model cannot be resolved; :meth:`load` returns ``None``
        only when the row itself is missing.

        Returns:
            Agent configurations in unspecified order.

        Raises:
            ValueError: If an agent's model or label cannot be resolved.
        """
        async with self._factory() as s:
            rows = (await s.execute(select(Agent))).scalars().all()
        specs: list[AgentSpec] = []
        for row in rows:
            spec = await self.load(row.name)
            if spec is not None:
                specs.append(spec)
        return specs

    async def delete(self, name: str) -> None:
        """Delete an agent configuration by name.

        Missing names are ignored. Tool, plugin, and mode binding rows and the
        cached ``AgentCard`` row are removed by foreign-key cascade when the
        commit lands. Deleting an agent still referenced by a session instead
        raises ``IntegrityError`` because ``SessionRow.agent_id`` uses
        ``RESTRICT``.

        Args:
            name: Agent configuration name.

        Raises:
            IntegrityError: If a session still references the agent.
        """
        async with self._factory() as s:
            row = (
                await s.execute(select(Agent).where(Agent.name == name))
            ).scalars().first()
            if row is not None:
                await s.delete(row)
                await s.commit()
                logger.info("agent deleted name={}", name)
