from agentbox_harness.lsp.diagnostics import (
    DiagnosticsReminder,
    get_diagnostics_service,
)
from agentbox_harness.lsp.manager import get_lsp_manager
from agentbox_harness.middleware import SessionReminder


def lsp_enabled() -> bool:
    service = get_diagnostics_service()
    return bool(get_lsp_manager().enabled and service.enabled)


def lsp_reminders() -> list[SessionReminder]:
    service = get_diagnostics_service()
    if not lsp_enabled() or service.mode != "auto":
        return []
    return [DiagnosticsReminder(service)]
