import json
import uuid

from sqlmodel import select

from agentbox_harness.spec import (
    AgentSpec,
    McpToolBinding,
    Mode,
    ModelBinding,
    NativeToolBinding,
)
from agentbox_models.tables.core import Agent, Model, Provider


def _serialize_bindings(bindings) -> str:
    return json.dumps([vars(b) for b in bindings])


def _serialize_modes(modes) -> str:
    return json.dumps([vars(m) for m in modes])


def _parse_bindings(raw: str):
    bindings = []
    for item in json.loads(raw or "[]"):
        if "server_url" in item:
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
            model = (
                await s.execute(
                    select(Model).where(Model.name == spec.model_binding.model)
                )
            ).scalars().first()
            if model is None:
                raise ValueError(f"Unknown model: {spec.model_binding.model}")

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
            row.tool_bindings = _serialize_bindings(spec.tool_bindings)
            row.mode_definitions = _serialize_modes(spec.mode_definitions)
            row.sub_agent_ids = json.dumps(spec.sub_agent_ids)
            s.add(row)
            await s.commit()
        return spec

    async def load(self, name: str) -> AgentSpec | None:
        async with self._factory() as s:
            row = (
                await s.execute(select(Agent).where(Agent.name == name))
            ).scalars().first()
            if row is None:
                return None
            model = (
                await s.execute(select(Model).where(Model.id == row.model_id))
            ).scalars().first()
            provider = (
                await s.execute(select(Provider).where(Provider.id == model.provider_id))
            ).scalars().first()
            return AgentSpec(
                name=row.name,
                description=row.description,
                instructions=row.instructions,
                tool_bindings=_parse_bindings(row.tool_bindings),
                mode_definitions=_parse_modes(row.mode_definitions),
                sub_agent_ids=json.loads(row.sub_agent_ids or "[]"),
                model_binding=ModelBinding(model=model.name, provider=provider.name),
            )

    async def delete(self, name: str) -> None:
        async with self._factory() as s:
            row = (
                await s.execute(select(Agent).where(Agent.name == name))
            ).scalars().first()
            if row is not None:
                await s.delete(row)
                await s.commit()
