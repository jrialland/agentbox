from collections.abc import Callable
from dataclasses import dataclass

from agentbox_harness.spec import Mode


@dataclass
class _Entry:
    callable: Callable
    required_flags: tuple[str, ...] = ()


class ToolRegistry:
    def __init__(self) -> None:
        self._native: dict[str, _Entry] = {}

    def register_native(
        self,
        name: str,
        callable: Callable,
        required_flags: tuple[str, ...] = (),
    ) -> None:
        self._native[name] = _Entry(callable, required_flags)

    def select_tools(self, mode: Mode) -> list[Callable]:
        return [
            entry.callable
            for entry in self._native.values()
            if all(mode.allows(f) for f in entry.required_flags)
        ]
