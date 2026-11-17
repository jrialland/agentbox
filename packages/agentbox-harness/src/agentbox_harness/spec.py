from pydantic import BaseModel
from pydantic.dataclasses import dataclass


@dataclass(frozen=True)
class ModelBinding:
    model: str
    provider: str


@dataclass(frozen=True)
class Mode:
    name: str
    flags: dict[str, bool]

    def allows(self, flag: str) -> bool:
        return self.flags.get(flag, True)


@dataclass(frozen=True)
class NativeToolBinding:
    name: str
    required_flags: tuple[str, ...] = ()


@dataclass(frozen=True)
class McpToolBinding:
    server_url: str
    tool_prefix: str = ""


ToolBinding = NativeToolBinding | McpToolBinding


class AgentSpec(BaseModel):
    name: str
    description: str
    instructions: str
    tool_bindings: list[ToolBinding]
    sub_agent_ids: list[str] = []
    mode_definitions: list[Mode] = []
    model_binding: ModelBinding


DEFAULT_MODES = (
    Mode(name="ask", flags={"write": False}),
    Mode(name="agent", flags={"write": True}),
)
