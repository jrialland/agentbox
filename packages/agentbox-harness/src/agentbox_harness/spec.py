from dataclasses import field

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
    server_url: str = ""
    tool_prefix: str = ""
    id: str = ""
    command: str = ""
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    env_passthrough: list[str] = field(default_factory=list)
    cwd: str = ""
    transport: str = ""
    headers: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class PluginMcpBinding:
    plugin: str
    server: str
    project_id: str | None = None
    id: str = ""


ToolBinding = NativeToolBinding | McpToolBinding


class AgentSpec(BaseModel):
    name: str
    description: str
    instructions: str
    tool_bindings: list[ToolBinding]
    mode_definitions: list[Mode] = []
    model_binding: ModelBinding
    model_label: str | None = None
    plugin_mcp_bindings: list[PluginMcpBinding] = []


DEFAULT_MODES = (
    Mode(name="ask", flags={"write": False}),
    Mode(name="agent", flags={"write": True}),
)
