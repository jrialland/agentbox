import functools
import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from loguru import logger

from agentbox_harness.spec import Mode


@dataclass
class ToolHookContext:
    tool_name: str
    args: dict
    root: object
    result: object


ToolHook = Callable[[ToolHookContext], Awaitable[str | None]]


@dataclass
class _Entry:
    callable: Callable
    required_flags: tuple[str, ...] = ()


class ToolRegistry:
    def __init__(self, hooks: list[ToolHook] | None = None, root=None) -> None:
        self._native: dict[str, _Entry] = {}
        self._hooks = list(hooks or [])
        self._root = root

    def register_native(
        self,
        name: str,
        callable: Callable,
        required_flags: tuple[str, ...] = (),
    ) -> None:
        fn = callable
        if self._hooks:
            original = callable

            @functools.wraps(original)
            async def wrapped(*args, **kwargs):
                result = await original(*args, **kwargs)
                try:
                    bound = inspect.signature(original).bind(*args, **kwargs)
                    call_args = dict(bound.arguments)
                except TypeError:
                    call_args = dict(kwargs)
                extras: list[str] = []
                for hook in self._hooks:
                    try:
                        extra = await hook(
                            ToolHookContext(
                                tool_name=name,
                                args=call_args,
                                root=self._root,
                                result=result,
                            )
                        )
                    except Exception:
                        logger.exception("tool hook failed tool={}", name)
                        continue
                    if extra:
                        extras.append(extra)
                if extras and isinstance(result, str):
                    return "\n\n".join([result, *extras])
                return result

            fn = wrapped
        self._native[name] = _Entry(fn, required_flags)

    def select_tools(
        self, mode: Mode, names: set[str] | None = None
    ) -> list[Callable]:
        result = []
        for name, entry in self._native.items():
            if names is not None and name not in names:
                continue
            if all(mode.allows(f) for f in entry.required_flags):
                result.append(entry.callable)
        return result
