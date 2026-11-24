"""Wire the harness LSP diagnostics service into API sessions.

Provides the enablement check and the reminder list handed to the harness.
Reminders are only produced when both the LSP manager and diagnostics service
are enabled and diagnostics run in ``auto`` mode; other modes require the model
to request diagnostics explicitly through a tool.
"""

from agentbox_harness.lsp.diagnostics import (
    DiagnosticsReminder,
    get_diagnostics_service,
)
from agentbox_harness.lsp.manager import get_lsp_manager
from agentbox_harness.middleware import SessionReminder


def lsp_enabled() -> bool:
    """Return whether both the LSP manager and diagnostics service are enabled.

    Returns:
        ``True`` only when the manager and diagnostics service are both on.
    """
    service = get_diagnostics_service()
    return bool(get_lsp_manager().enabled and service.enabled)


def lsp_reminders() -> list[SessionReminder]:
    """Return session reminders for automatic LSP diagnostics.

    In ``auto`` mode a diagnostics reminder is attached so the harness runs
    diagnostics without an explicit tool call; every other mode, or a disabled
    service, yields no reminders.

    Returns:
        A single-element reminder list when auto diagnostics are active, else an
        empty list.
    """
    service = get_diagnostics_service()
    if not lsp_enabled() or service.mode != "auto":
        return []
    return [DiagnosticsReminder(service)]
