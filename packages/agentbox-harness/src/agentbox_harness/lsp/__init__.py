"""LSP integration: stack detection and language-server process management."""

from agentbox_harness.lsp.detect import detect_stacks
from agentbox_harness.lsp.stacks import DEFAULT_LSP_SERVERS, LspStack, language_for

__all__ = ["DEFAULT_LSP_SERVERS", "LspStack", "detect_stacks", "language_for"]
