import json
import uuid

from loguru import logger
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
from agentbox_models.tables.core import Agent, Model, Provider


def _serialize_bindings(bindings) -> str:
    return json.dumps([vars(b) for b in bindings])


def _serialize_modes(modes) -> str:
    return json.dumps([vars(m) for m in modes])


def _parse_bindings(raw: str):
    bindings = []
    for item in json.loads(raw or "[]"):
        if "server_url" in item or "command" in item:
            bindings.append(McpToolBinding(**item))
        else:
            bindings.append(NativeToolBinding(**item))
    return bindings


def _parse_modes(raw: str) -> list[Mode]:
    return [Mode(**item) for item in json.loads(raw or "[]")]


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
                await s.execute(select(Provider).where(Provider.id == model.provider_id))
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
            row.tool_bindings = _serialize_bindings(spec.tool_bindings)
            row.mode_definitions = _serialize_modes(spec.mode_definitions)
            s.add(row)
            await s.commit()
            logger.info("agent saved name={}", spec.name)
        return spec.model_copy(
            update={
                "model_binding": ModelBinding(model=model.name, provider=provider.name),
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
                await s.execute(select(Provider).where(Provider.id == model.provider_id))
            ).scalars().first()
            return AgentSpec(
                name=row.name,
                description=row.description,
                instructions=row.instructions,
                tool_bindings=_parse_bindings(row.tool_bindings),
                mode_definitions=_parse_modes(row.mode_definitions),
                model_binding=ModelBinding(model=model.name, provider=provider.name),
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
