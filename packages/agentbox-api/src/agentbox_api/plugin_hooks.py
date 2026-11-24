"""Execute plugin hooks at session, run, and tool lifecycle events.

Hooks run in declaration order. Most hook failures are logged and skipped so a
broken plugin cannot break a session; the exception is a ``before_tool`` hook
configured with ``on_error=deny``, which fails the tool. Command hooks spawn
subprocesses and HTTP hooks make network requests, both bounded by timeouts and
output limits.
"""

from __future__ import annotations

import asyncio
import dataclasses
import fnmatch
import json
import os
import pathlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
from loguru import logger
from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.exceptions import ToolFailed
from pydantic_ai.messages import SystemPromptPart, ToolCallPart, ToolReturn
from pydantic_ai.tools import RunContext, ToolDefinition

from agentbox_api.plugin_hook_config import (
    TOOL_EVENTS,
    CommandAction,
    ContextAction,
    HttpAction,
    PluginHook,
)
from agentbox_api.plugin_validation import validate_headers, validate_url

PLUGIN_HOOKS_MAX_OUTPUT_BYTES = 64 * 1024
PLUGIN_HOOKS_MAX_CONTEXT_CHARS = 8_000
_ENV_PASSTHROUGH = (
    "PATH",
    "PATHEXT",
    "SystemRoot",
    "WINDIR",
    "HOME",
    "USERPROFILE",
    "TEMP",
    "TMP",
)


class HookExecutionError(RuntimeError):
    """Raised when a hook action fails or returns an invalid response."""


@dataclass(frozen=True)
class HookContext:
    """Payload describing the event a hook is invoked for.

    Fields not relevant to an event stay at their defaults. ``payload`` renders
    a JSON-safe view passed to command stdin and HTTP bodies.
    """

    event: str
    session_id: str = ""
    project_id: str | None = None
    project_root: str = ""
    run_id: str | None = None
    tool_name: str | None = None
    tool_call_id: str | None = None
    args: dict[str, Any] | None = None
    result: Any = None
    error: dict[str, Any] | None = None
    plugin: str = ""
    hook_id: str = ""
    plugin_root: str = ""
    plugin_data: str = ""
    timestamp: str = ""

    def payload(self) -> dict[str, Any]:
        """Return a JSON-safe mapping describing this event."""
        return {
            "event": self.event,
            "plugin": self.plugin,
            "hook_id": self.hook_id,
            "session_id": self.session_id,
            "project_id": self.project_id,
            "project_root": self.project_root,
            "run_id": self.run_id,
            "tool_name": self.tool_name,
            "tool_call_id": self.tool_call_id,
            "args": _jsonable(self.args),
            "result": _jsonable(self.result),
            "error": _jsonable(self.error),
            "plugin_root": self.plugin_root,
            "plugin_data": self.plugin_data,
            "timestamp": self.timestamp or datetime.now(UTC).isoformat(),
        }


@dataclass(frozen=True)
class HookResult:
    """Parsed response from a hook action.

    ``decision`` and ``args`` are only honored for ``before_tool``; ``result``
    replaces tool output for ``after_tool``/``tool_error``; ``context`` is
    injected into the model context.
    """

    decision: str | None = None
    reason: str = ""
    args: dict[str, Any] | None = None
    result: Any = None
    context: str = ""


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, bytes):
        return {"type": "binary", "size": len(value)}
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    if dataclasses.is_dataclass(value):
        return _jsonable(dataclasses.asdict(value))
    if hasattr(value, "model_dump"):
        return _jsonable(value.model_dump())
    return str(value)


def _parse_response(text: str) -> HookResult:
    stripped = text.strip()
    if not stripped:
        return HookResult()
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        return HookResult(context=stripped[:PLUGIN_HOOKS_MAX_CONTEXT_CHARS])
    if not isinstance(data, dict):
        return HookResult(context=stripped[:PLUGIN_HOOKS_MAX_CONTEXT_CHARS])
    decision = data.get("decision")
    if decision not in (None, "allow", "deny"):
        raise HookExecutionError("invalid decision")
    args = data.get("args")
    if args is not None and not isinstance(args, dict):
        raise HookExecutionError("args must be an object")
    context = data.get("context")
    if context is not None and not isinstance(context, str):
        raise HookExecutionError("context must be a string")
    return HookResult(
        decision=decision,
        reason=str(data.get("reason") or ""),
        args=args,
        result=data.get("result"),
        context=(context or "")[:PLUGIN_HOOKS_MAX_CONTEXT_CHARS],
    )


class HookExecutor:
    """Run a single hook action and parse its response."""

    async def execute(self, hook: PluginHook, context: HookContext) -> HookResult:
        """Execute one hook action for the given event.

        Args:
            hook: Hook declaration whose action should run.
            context: Event payload passed to the action.

        Returns:
            The parsed hook result.

        Raises:
            HookExecutionError: If the action fails or its response is invalid.
        """
        action = hook.action
        if isinstance(action, ContextAction):
            return HookResult(
                context=action.text[:PLUGIN_HOOKS_MAX_CONTEXT_CHARS]
            )
        if isinstance(action, CommandAction):
            text = await self._run_command(action, context)
        elif isinstance(action, HttpAction):
            text = await self._run_http(action, context)
        else:
            raise HookExecutionError(f"unsupported hook action: {action.type}")
        return _parse_response(text)

    async def _run_command(
        self, action: CommandAction, context: HookContext
    ) -> str:
        env = {
            key: os.environ[key]
            for key in _ENV_PASSTHROUGH
            if key in os.environ
        }
        env.update(action.env)
        env["PLUGIN_ROOT"] = context.plugin_root
        env["PLUGIN_DATA"] = context.plugin_data
        env["AGENTBOX_EVENT"] = context.event
        env["AGENTBOX_PROJECT_ROOT"] = context.project_root
        env["AGENTBOX_SESSION_ID"] = context.session_id
        if context.run_id:
            env["AGENTBOX_RUN_ID"] = context.run_id
        if context.tool_name:
            env["AGENTBOX_TOOL_NAME"] = context.tool_name

        cwd = action.cwd or context.project_root or context.plugin_root or None
        payload = json.dumps(
            context.payload(), ensure_ascii=False, default=str
        ).encode("utf-8")
        try:
            process = await asyncio.create_subprocess_exec(
                action.command,
                *action.args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=env,
            )
        except OSError as exc:
            raise HookExecutionError(f"cannot start command: {exc}") from exc

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(payload), timeout=action.timeout_ms / 1000
            )
        except TimeoutError as exc:
            process.kill()
            await process.wait()
            raise HookExecutionError("command timed out") from exc

        if len(stdout) > PLUGIN_HOOKS_MAX_OUTPUT_BYTES:
            raise HookExecutionError("command stdout exceeds limit")
        if process.returncode:
            detail = stderr.decode("utf-8", "replace").strip()[:1000]
            raise HookExecutionError(
                f"command exited with {process.returncode}: {detail}"
            )
        return stdout.decode("utf-8", "replace")

    async def _run_http(self, action: HttpAction, context: HookContext) -> str:
        validate_url(action.url)
        headers = validate_headers(action.headers)
        try:
            async with httpx.AsyncClient(
                timeout=action.timeout_ms / 1000,
                follow_redirects=False,
            ) as client:
                response = await client.request(
                    action.method,
                    action.url,
                    json=context.payload(),
                    headers=headers,
                )
        except httpx.HTTPError as exc:
            raise HookExecutionError(f"http hook failed: {exc}") from exc
        if not 200 <= response.status_code < 300:
            raise HookExecutionError(
                f"http hook returned {response.status_code}"
            )
        if len(response.content) > PLUGIN_HOOKS_MAX_OUTPUT_BYTES:
            raise HookExecutionError("http response exceeds limit")
        return response.text

@dataclass(frozen=True)
class PluginHookRef:
    """A hook together with the plugin paths it runs against."""

    plugin: str
    root: pathlib.Path
    data: pathlib.Path
    hook: PluginHook


@dataclass(frozen=True)
class SessionHookState:
    """Hook refs and project metadata retained for an active session."""

    refs: tuple[PluginHookRef, ...]
    project_id: str | None
    project_root: str


def _error_dict(error: BaseException) -> dict[str, str]:
    return {
        "type": type(error).__name__,
        "message": str(error)[:2000],
    }


def _applies(ref: PluginHookRef, event: str, tool_name: str | None) -> bool:
    if ref.hook.event != event:
        return False
    if event in TOOL_EVENTS and ref.hook.tools:
        name = tool_name or ""
        return any(fnmatch.fnmatchcase(name, pattern) for pattern in ref.hook.tools)
    return True


def _context_for(
    ref: PluginHookRef, event: str, base: HookContext
) -> HookContext:
    return dataclasses.replace(
        base,
        event=event,
        plugin=ref.plugin,
        hook_id=ref.hook.id,
        plugin_root=str(ref.root),
        plugin_data=str(ref.data),
    )


async def _run_context_refs(
    executor: HookExecutor,
    refs: tuple[PluginHookRef, ...],
    event: str,
    base: HookContext,
    tool_name: str | None = None,
) -> tuple[str, ...]:
    contexts: list[str] = []
    # Run in declaration order so context is deterministic, and isolate failures
    # so one broken hook cannot suppress later hooks or the event itself.
    for ref in refs:
        if not _applies(ref, event, tool_name):
            continue
        try:
            result = await executor.execute(ref.hook, _context_for(ref, event, base))
        except Exception as exc:
            logger.warning(
                "plugin hook failed id={} event={} error={}",
                ref.hook.id,
                event,
                exc,
            )
            continue
        if result.context:
            contexts.append(result.context)
    return tuple(contexts)


async def _run_side_effect_refs(
    executor: HookExecutor,
    refs: tuple[PluginHookRef, ...],
    event: str,
    base: HookContext,
    tool_name: str | None = None,
) -> None:
    await _run_context_refs(executor, refs, event, base, tool_name)


async def _run_before_tool(
    executor: HookExecutor,
    refs: tuple[PluginHookRef, ...],
    base: HookContext,
    args: dict[str, Any],
    tool_name: str | None,
) -> tuple[dict[str, Any], list[str]]:
    contexts: list[str] = []
    # Rewrites accumulate into the args returned to the tool, but each hook's
    # payload reflects the original args. Failures are skipped unless the hook
    # opted into ``on_error=deny``.
    for ref in refs:
        if not _applies(ref, "before_tool", tool_name):
            continue
        try:
            result = await executor.execute(
                ref.hook, _context_for(ref, "before_tool", base)
            )
        except Exception as exc:
            if ref.hook.on_error == "deny":
                raise ToolFailed(
                    f"plugin hook {ref.hook.id} failed: {exc}"
                ) from exc
            logger.warning(
                "plugin hook failed id={} event=before_tool error={}",
                ref.hook.id,
                exc,
            )
            continue
        if result.decision == "deny":
            reason = result.reason or f"denied by plugin {ref.plugin} hook {ref.hook.id}"
            raise ToolFailed(reason)
        if result.args is not None:
            args = result.args
        if result.context:
            contexts.append(result.context)
    return args, contexts


async def _run_after_tool(
    executor: HookExecutor,
    refs: tuple[PluginHookRef, ...],
    base: HookContext,
    result: Any,
    tool_name: str | None,
) -> tuple[Any, list[str]]:
    contexts: list[str] = []
    # Later hooks can observe and replace earlier results; failures are isolated.
    for ref in refs:
        if not _applies(ref, "after_tool", tool_name):
            continue
        try:
            hook_result = await executor.execute(
                ref.hook, _context_for(ref, "after_tool", base)
            )
        except Exception as exc:
            logger.warning(
                "plugin hook failed id={} event=after_tool error={}",
                ref.hook.id,
                exc,
            )
            continue
        if hook_result.result is not None:
            result = hook_result.result
        if hook_result.context:
            contexts.append(hook_result.context)
    return result, contexts


async def _run_tool_error(
    executor: HookExecutor,
    refs: tuple[PluginHookRef, ...],
    base: HookContext,
    tool_name: str | None,
) -> tuple[Any, list[str]]:
    replacement: Any = None
    contexts: list[str] = []
    # Error hooks may supply replacement output; failures remain isolated so the
    # original error still surfaces when nothing handles it.
    for ref in refs:
        if not _applies(ref, "tool_error", tool_name):
            continue
        try:
            hook_result = await executor.execute(
                ref.hook, _context_for(ref, "tool_error", base)
            )
        except Exception as exc:
            logger.warning(
                "plugin hook failed id={} event=tool_error error={}",
                ref.hook.id,
                exc,
            )
            continue
        if hook_result.result is not None:
            replacement = hook_result.result
        if hook_result.context:
            contexts.append(hook_result.context)
    return replacement, contexts


def _append_context(result: Any, context: str) -> Any:
    if not context:
        return result
    if isinstance(result, ToolReturn):
        if isinstance(result.return_value, str):
            return dataclasses.replace(
                result,
                return_value=f"{result.return_value}\n\n{context}",
            )
        if isinstance(result.content, str):
            return dataclasses.replace(
                result,
                content=f"{result.content}\n\n{context}",
            )
        if isinstance(result.content, (list, tuple)):
            return dataclasses.replace(
                result,
                content=[*result.content, context],
            )
        return dataclasses.replace(result, content=context)
    if isinstance(result, str):
        return f"{result}\n\n{context}"
    return f"{result}\n\n{context}"


class PluginHookRuntime:
    """Track active sessions and run their session-scoped hooks.

    ``session_start`` fires once per session; ``session_end`` fires when the
    session is torn down. State is process-local.
    """

    def __init__(self, executor: HookExecutor | None = None):
        self.started: set[str] = set()
        self.active: dict[str, SessionHookState] = {}
        self.executor = executor or HookExecutor()

    async def ensure_started(
        self,
        session_id: str,
        refs: tuple[PluginHookRef, ...],
        project_id: str | None,
        project_root: str,
    ) -> tuple[str, ...]:
        """Start a session's hooks once and return any start context.

        Args:
            session_id: Session being started.
            refs: Hooks enabled for the session.
            project_id: Project owning the session, if any.
            project_root: Project root passed to hooks.

        Returns:
            Context strings emitted by ``session_start`` hooks; empty when the
            session was already started.
        """
        if session_id in self.started:
            return ()
        self.started.add(session_id)
        self.active[session_id] = SessionHookState(
            tuple(refs), project_id, project_root
        )
        base = HookContext(
            event="session_start",
            session_id=session_id,
            project_id=project_id,
            project_root=project_root,
        )
        return await _run_context_refs(
            self.executor, tuple(refs), "session_start", base
        )

    async def end_session(self, session_id: str) -> None:
        """Fire ``session_end`` hooks and forget the session's state.

        Args:
            session_id: Session being torn down.
        """
        state = self.active.pop(session_id, None)
        self.started.discard(session_id)
        if state is None or not state.refs:
            return
        base = HookContext(
            event="session_end",
            session_id=session_id,
            project_id=state.project_id,
            project_root=state.project_root,
        )
        await _run_side_effect_refs(
            self.executor, state.refs, "session_end", base
        )

    async def end_all(self) -> None:
        """End every active session, firing their ``session_end`` hooks."""
        for session_id in list(self.active):
            await self.end_session(session_id)


_runtime: PluginHookRuntime | None = None


def get_plugin_hook_runtime() -> PluginHookRuntime:
    """Return the process-wide plugin hook runtime, creating it on first use."""
    global _runtime
    if _runtime is None:
        _runtime = PluginHookRuntime()
    return _runtime


class PluginHooks(AbstractCapability[Any]):
    """pydantic-ai capability that runs plugin hooks for one session.

    It maps run and tool lifecycle callbacks onto the session's hook refs,
    enqueues hook-provided context into the system prompt, and rewrites or
    replaces tool args/results where hooks request it.
    """

    def __init__(
        self,
        runtime: PluginHookRuntime,
        session_id: str,
        project_id: str | None,
        project_root: str,
        refs: tuple[PluginHookRef, ...],
    ):
        self.runtime = runtime
        self.session_id = session_id
        self.project_id = project_id
        self.project_root = project_root
        self.refs = tuple(refs)
        self._tool_context: dict[str, list[str]] = {}

    def _base(self, event: str, ctx: RunContext[Any], **kwargs: Any) -> HookContext:
        return HookContext(
            event=event,
            session_id=self.session_id,
            project_id=self.project_id,
            project_root=self.project_root,
            run_id=getattr(ctx, "run_id", None),
            **kwargs,
        )

    async def before_run(self, ctx: RunContext[Any]) -> None:
        """Start the session and run start hooks, enqueuing their context.

        Args:
            ctx: pydantic-ai run context for the current run.
        """
        session_context = await self.runtime.ensure_started(
            self.session_id,
            self.refs,
            self.project_id,
            self.project_root,
        )
        run_context = await _run_context_refs(
            self.runtime.executor,
            self.refs,
            "run_start",
            self._base("run_start", ctx),
        )
        content = "\n\n".join([*session_context, *run_context])
        if content:
            ctx.enqueue(SystemPromptPart(content=content, scope="request"))

    async def after_run(
        self, ctx: RunContext[Any], *, result: Any
    ) -> Any:
        """Fire run end hooks and return the run result unchanged.

        Args:
            ctx: pydantic-ai run context for the finished run.
            result: Result produced by the run.

        Returns:
            ``result`` unchanged, since end hooks are side-effect only.
        """
        await _run_side_effect_refs(
            self.runtime.executor,
            self.refs,
            "run_end",
            self._base("run_end", ctx, result=result),
        )
        return result

    async def on_run_error(
        self, ctx: RunContext[Any], *, error: BaseException
    ) -> Any:
        """Fire run error hooks, then re-raise the original error.

        Args:
            ctx: pydantic-ai run context for the failed run.
            error: Exception that ended the run.

        Raises:
            BaseException: The original ``error``, always re-raised.
        """
        await _run_side_effect_refs(
            self.runtime.executor,
            self.refs,
            "run_error",
            self._base("run_error", ctx, error=_error_dict(error)),
        )
        raise error

    async def before_tool_execute(
        self,
        ctx: RunContext[Any],
        *,
        call: ToolCallPart,
        tool_def: ToolDefinition,
        args: dict[str, Any],
    ) -> dict[str, Any]:
        """Run before-tool hooks, returning possibly rewritten arguments.

        Args:
            ctx: pydantic-ai run context.
            call: Tool call being executed.
            tool_def: Definition of the tool being executed.
            args: Arguments the model supplied for the call.

        Returns:
            The arguments to execute with, after any hook rewrites.

        Raises:
            ToolFailed: If a hook denies the call or fails with
                ``on_error=deny``.
        """
        base = self._base(
            "before_tool",
            ctx,
            tool_name=call.tool_name,
            tool_call_id=call.tool_call_id,
            args=args,
        )
        new_args, contexts = await _run_before_tool(
            self.runtime.executor,
            self.refs,
            base,
            args,
            call.tool_name,
        )
        key = call.tool_call_id or ""
        if contexts:
            self._tool_context[key] = contexts
        return new_args

    async def after_tool_execute(
        self,
        ctx: RunContext[Any],
        *,
        call: ToolCallPart,
        tool_def: ToolDefinition,
        args: dict[str, Any],
        result: Any,
    ) -> Any:
        """Run after-tool hooks and append any stored hook context.

        Args:
            ctx: pydantic-ai run context.
            call: Tool call that completed.
            tool_def: Definition of the executed tool.
            args: Arguments the tool ran with.
            result: Tool output before hooks.

        Returns:
            The tool output after hooks and appended context.
        """
        base = self._base(
            "after_tool",
            ctx,
            tool_name=call.tool_name,
            tool_call_id=call.tool_call_id,
            args=args,
            result=result,
        )
        result, contexts = await _run_after_tool(
            self.runtime.executor,
            self.refs,
            base,
            result,
            call.tool_name,
        )
        key = call.tool_call_id or ""
        before_contexts = self._tool_context.pop(key, [])
        for context in [*before_contexts, *contexts]:
            result = _append_context(result, context)
        return result

    async def on_tool_execute_error(
        self,
        ctx: RunContext[Any],
        *,
        call: ToolCallPart,
        tool_def: ToolDefinition,
        args: dict[str, Any],
        error: Exception,
    ) -> Any:
        """Run tool-error hooks and decide how the error surfaces.

        Args:
            ctx: pydantic-ai run context.
            call: Tool call that failed.
            tool_def: Definition of the failed tool.
            args: Arguments the tool ran with.
            error: Exception raised by the tool.

        Returns:
            Replacement output when a hook supplied one.

        Raises:
            ToolFailed: When hooks emitted context but no replacement.
            Exception: The original ``error`` when no hook handled it.
        """
        base = self._base(
            "tool_error",
            ctx,
            tool_name=call.tool_name,
            tool_call_id=call.tool_call_id,
            args=args,
            error=_error_dict(error),
        )
        self._tool_context.pop(call.tool_call_id or "", None)
        replacement, contexts = await _run_tool_error(
            self.runtime.executor,
            self.refs,
            base,
            call.tool_name,
        )
        if replacement is not None:
            for context in contexts:
                replacement = _append_context(replacement, context)
            return replacement
        if contexts:
            message = "\n\n".join([*contexts, str(error)])
            raise ToolFailed(message) from error
        raise error
