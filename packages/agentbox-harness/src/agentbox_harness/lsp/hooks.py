from loguru import logger

from agentbox_harness.lsp.stacks import language_for
from agentbox_harness.tools.registry import ToolHookContext

WRITE_TOOLS = {"write_file", "append_file", "edit_file"}


def format_diagnostics(path: str, diagnostics: list[dict]) -> str | None:
    rows = []
    for diagnostic in diagnostics:
        severity = diagnostic.get("severity", 1)
        if severity not in (1, 2):
            continue
        start = diagnostic.get("range", {}).get("start", {})
        line = start.get("line", 0) + 1
        column = start.get("character", 0) + 1
        level = "error" if severity == 1 else "warning"
        source = f" ({diagnostic['source']})" if diagnostic.get("source") else ""
        rows.append(
            f"  {line}:{column} {level} {diagnostic.get('message', '')}{source}"
        )
    if not rows:
        return None
    suffix = f"\n  ... and {len(rows) - 10} more" if len(rows) > 10 else ""
    return f"LSP diagnostics for {path}:\n" + "\n".join(rows[:10]) + suffix


def make_lsp_hook(manager, session_id: str | None, project_root: str):
    async def hook(ctx: ToolHookContext) -> str | None:
        if ctx.tool_name not in WRITE_TOOLS or not manager.enabled:
            return None
        path = ctx.args.get("path")
        if not path:
            return None
        resolved = await manager.server_for_path(project_root, path)
        if resolved is None:
            return None
        stack, root, server = resolved
        language = language_for(stack, path)
        if language is None:
            return None
        await server.sync_document(path, language, save=stack.save)
        diagnostics = await server.diagnostics(path)
        logger.debug(
            "lsp hook done stack={} path={} count={}",
            stack.name,
            path,
            len(diagnostics),
        )
        if session_id:
            manager.record_active(session_id, str(root), stack, server)
        return format_diagnostics(path, diagnostics)

    return hook
