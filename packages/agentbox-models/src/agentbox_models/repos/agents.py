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
)
from agentbox_models.repos.model_labels import (
    canonical_label,
    resolve_model_label,
)
from agentbox_models.tables.core import (
    Agent,
    AgentMode,
    AgentModeFlag,
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
        delete(AgentToolBinding).where(AgentToolBinding.agent_id == agent_id)
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
            .order_by(AgentToolBinding.position)
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
                .order_by(AgentToolBindingArg.position)
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
                .order_by(AgentToolBindingEnvPassthrough.position)
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


async def _save_modes(session, agent_id: str, modes) -> None:
    await session.execute(delete(AgentMode).where(AgentMode.agent_id == agent_id))
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
            .order_by(AgentMode.position)
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
    def __init__(self, session_factory):
        self._factory = session_factory

    async def save(self, spec: AgentSpec) -> AgentSpec:
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
            await s.flush()
            await _save_bindings(s, row.id, spec.tool_bindings)
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
                mode_definitions=await _load_modes(s, row.id),
                model_binding=ModelBinding(
                    model=model.name, provider=provider.name
                ),
                model_label=row.model_label,
            )

    async def list(self) -> list[AgentSpec]:
        async with self._factory() as s:
            rows = (await s.execute(select(Agent))).scalars().all()
        specs: list[AgentSpec] = []
        for row in rows:
            spec = await self.load(row.name)
            if spec is not None:
                specs.append(spec)
        return specs

    async def delete(self, name: str) -> None:
        async with self._factory() as s:
            row = (
                await s.execute(select(Agent).where(Agent.name == name))
            ).scalars().first()
            if row is not None:
                await s.delete(row)
                await s.commit()
                logger.info("agent deleted name={}", name)
