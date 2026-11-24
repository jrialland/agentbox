"""Agent configuration types for the harness.

An :class:`AgentSpec` describes an Agent (model, instructions, tools, and
modes). It is configuration only; live execution happens in a session.
"""

from dataclasses import field

from pydantic import BaseModel
from pydantic.dataclasses import dataclass


@dataclass(frozen=True)
class ModelBinding:
    """Select the model name and provider for an Agent configuration."""

    model: str
    provider: str


@dataclass(frozen=True)
class Mode:
    """A named session mode with boolean feature flags."""

    name: str
    flags: dict[str, bool]

    def allows(self, flag: str) -> bool:
        """Return whether the mode permits a flag.

        Unset flags default to allowed.

        Args:
            flag: Flag name to look up.

        Returns:
            ``True`` when the flag is absent or set to ``True``.
        """
        return self.flags.get(flag, True)


@dataclass(frozen=True)
class NativeToolBinding:
    """Bind a built-in harness tool that requires certain mode flags."""

    name: str
    required_flags: tuple[str, ...] = ()


@dataclass(frozen=True)
class McpToolBinding:
    """Connect an MCP server and optionally prefix the tools it exposes."""

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
    """Reference an MCP server provided by a plugin."""

    plugin: str
    server: str
    project_id: str | None = None
    id: str = ""


ToolBinding = NativeToolBinding | McpToolBinding


class AgentSpec(BaseModel):
    """Configuration record describing an Agent.

    An Agent is not a running unit; a session instantiates this configuration.
    """

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
