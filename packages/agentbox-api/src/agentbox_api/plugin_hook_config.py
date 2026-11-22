from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from agentbox_api.plugin_validation import (
    RESERVED_ENV,
    ensure_inside,
    expand,
    resolve_cwd,
    validate_headers,
    validate_url,
)

HookEvent = Literal[
    "session_start",
    "session_end",
    "run_start",
    "run_end",
    "run_error",
    "before_tool",
    "after_tool",
    "tool_error",
]
TOOL_EVENTS = frozenset({"before_tool", "after_tool", "tool_error"})
MAX_HOOKS = 50
DEFAULT_TIMEOUT_MS = 5_000
MAX_TIMEOUT_MS = 30_000
_HTTP_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE", "GET"})


@dataclass(frozen=True)
class HookIssue:
    severity: Literal["warning"]
    component: str
    message: str


class CommandAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["command"]
    command: str = Field(min_length=1)
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    cwd: str = ""
    timeout_ms: int = DEFAULT_TIMEOUT_MS

    @field_validator("timeout_ms")
    @classmethod
    def _timeout(cls, value: int) -> int:
        return min(MAX_TIMEOUT_MS, max(100, value))


class HttpAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["http"]
    url: str = Field(min_length=1)
    method: str = "POST"
    headers: dict[str, str] = Field(default_factory=dict)
    timeout_ms: int = DEFAULT_TIMEOUT_MS

    @field_validator("method")
    @classmethod
    def _method(cls, value: str) -> str:
        method = value.upper()
        if method not in _HTTP_METHODS:
            raise ValueError(f"unsupported HTTP method: {value}")
        return method

    @field_validator("timeout_ms")
    @classmethod
    def _timeout(cls, value: int) -> int:
        return min(MAX_TIMEOUT_MS, max(100, value))


class ContextAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["context"]
    text: str = Field(min_length=1)


HookAction = Annotated[
    CommandAction | HttpAction | ContextAction,
    Field(discriminator="type"),
]


class PluginHook(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$",
    )
    event: HookEvent
    tools: list[str] = Field(default_factory=list)
    action: HookAction
    on_error: Literal["ignore", "deny"] = "ignore"

    @field_validator("tools")
    @classmethod
    def _tools(cls, value: list[str]) -> list[str]:
        if any(not item.strip() for item in value):
            raise ValueError("tools patterns must not be empty")
        return value

    @model_validator(mode="after")
    def _scope(self) -> PluginHook:
        if self.tools and self.event not in TOOL_EVENTS:
            raise ValueError("tools is only valid for tool events")
        if self.on_error == "deny" and self.event != "before_tool":
            raise ValueError("on_error=deny is only valid for before_tool")
        return self


class HooksFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal[1]
    hooks: list[Any]


def _normalize_hook(
    hook: PluginHook, root: pathlib.Path, data_root: pathlib.Path
) -> PluginHook:
    action = hook.action
    if isinstance(action, CommandAction):
        command = action.command
        if command.startswith("./"):
            command = str(ensure_inside(root, root / command[2:]))
        elif "/" in command or "\\" in command:
            raise ValueError("command must be bare or start with ./")
        args = [expand(value, root, data_root) for value in action.args]
        env: dict[str, str] = {}
        for key, value in action.env.items():
            if key in RESERVED_ENV:
                raise ValueError(f"reserved environment variable: {key}")
            env[key] = expand(value, root, data_root)
        cwd = (
            resolve_cwd(action.cwd, root, data_root) if action.cwd else ""
        )
        action = action.model_copy(
            update={"command": command, "args": args, "env": env, "cwd": cwd}
        )
    elif isinstance(action, HttpAction):
        validate_url(action.url)
        headers = validate_headers(action.headers)
        action = action.model_copy(update={"headers": headers})
    return hook.model_copy(update={"action": action})


def load_plugin_hooks(
    root: pathlib.Path, data_root: pathlib.Path
) -> tuple[tuple[PluginHook, ...], tuple[HookIssue, ...]]:
    issues: list[HookIssue] = []
    path = root / "com.agentbox" / "hooks" / "hooks.json"
    if not path.exists():
        return (), ()
    if not path.is_file():
        issues.append(
            HookIssue("warning", "com.agentbox:hooks", "hooks.json is not a file")
        )
        return (), tuple(issues)
    try:
        ensure_inside(root, path)
    except ValueError:
        issues.append(
            HookIssue(
                "warning",
                "com.agentbox:hooks",
                "hooks.json escapes plugin root",
            )
        )
        return (), tuple(issues)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        parsed = HooksFile.model_validate(raw)
    except (OSError, ValueError, ValidationError) as exc:
        issues.append(
            HookIssue("warning", "com.agentbox:hooks", f"invalid hooks.json: {exc}")
        )
        return (), tuple(issues)

    hooks: list[PluginHook] = []
    seen: set[str] = set()
    for index, item in enumerate(parsed.hooks):
        raw_id = item.get("id") if isinstance(item, dict) else None
        component = f"com.agentbox:hook:{raw_id or index}"
        try:
            hook = PluginHook.model_validate(item)
        except ValidationError as exc:
            issues.append(HookIssue("warning", component, exc.errors()[0]["msg"]))
            continue
        if hook.id in seen:
            issues.append(
                HookIssue("warning", component, f"duplicate hook id: {hook.id}")
            )
            continue
        seen.add(hook.id)
        if len(hooks) >= MAX_HOOKS:
            issues.append(
                HookIssue(
                    "warning",
                    component,
                    f"plugin has more than {MAX_HOOKS} hooks",
                )
            )
            continue
        try:
            hooks.append(_normalize_hook(hook, root, data_root))
        except ValueError as exc:
            issues.append(HookIssue("warning", component, str(exc)))
    return tuple(hooks), tuple(issues)
