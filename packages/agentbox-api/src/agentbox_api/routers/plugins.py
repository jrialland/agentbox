"""Agent Plugin discovery and enable/disable endpoints.

Plugins are installed globally or per project and can contribute skills, MCP
servers, and hooks. Reads require ``plugins:read``; toggling requires
``plugins:write``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import select

from agentbox_api.deps import require_permission
from agentbox_api.plugin_service import PluginService, PluginView
from agentbox_models.tables.core import Project

router = APIRouter(prefix="/plugins", tags=["plugins"])


class PluginStateBody(BaseModel):
    """Request body for enabling or disabling a plugin.

    ``scope`` is ``global`` or ``project``; project scope requires
    ``project_id``.
    """

    plugin_name: str
    scope: str = "global"
    project_id: str | None = None
    enabled: bool = True


def _service(request: Request) -> PluginService:
    settings = request.app.state.settings
    return PluginService(
        request.app.state.session_factory,
        settings.plugins_user_dir,
        settings.plugins_data_dir,
    )


async def _project(request: Request, project_id: str | None) -> Project | None:
    if not project_id:
        return None
    async with request.app.state.session_factory() as s:
        project = (
            await s.execute(select(Project).where(Project.id == project_id))
        ).scalars().first()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _serialize(view: PluginView) -> dict:
    manifest = view.loaded.manifest
    return {
        "name": view.name,
        "version": view.version,
        "description": view.description,
        "scope": view.scope,
        "project_id": view.project_id,
        "enabled": view.enabled,
        "valid": view.valid,
        "shadowed": view.shadowed,
        "author": manifest.author if manifest else {},
        "homepage": manifest.homepage if manifest else "",
        "repository": manifest.repository if manifest else "",
        "license": manifest.license if manifest else "",
        "keywords": list(manifest.keywords) if manifest else [],
        "skills": [
            {
                "name": skill.scoped_name,
                "description": skill.description,
            }
            for skill in view.skills
        ],
        "mcp_servers": [
            {"name": server.name, "transport": server.transport}
            for server in view.mcp_servers
        ],
        "hooks": [
            {
                "id": hook.id,
                "event": hook.event,
                "tools": list(hook.tools),
                "action": hook.action.type,
                "command": getattr(hook.action, "command", ""),
                "url": getattr(hook.action, "url", ""),
                "timeout_ms": getattr(hook.action, "timeout_ms", 0),
                "on_error": hook.on_error,
            }
            for hook in view.hooks
        ],
        "issues": [
            {
                "severity": issue.severity,
                "component": issue.component,
                "message": issue.message,
            }
            for issue in view.issues
        ],
    }


@router.get("")
async def list_plugins(
    request: Request,
    project_id: str | None = None,
    _=Depends(require_permission("plugins:read")),
):
    """List installed plugins visible to the caller.

    Requires the ``plugins:read`` permission. Passing ``project_id`` includes
    project-scoped plugins for that project.

    Returns:
        Plugin summaries, or 404 when ``project_id`` does not exist.
    """
    project = await _project(request, project_id)
    views = await _service(request).list_plugins(
        project.id if project else None,
        project.path if project else ".",
    )
    return [_serialize(view) for view in views]


@router.get("/{scope}/{name}")
async def get_plugin(
    scope: str,
    name: str,
    request: Request,
    project_id: str | None = None,
    _=Depends(require_permission("plugins:read")),
):
    """Get one plugin by scope and name.

    Requires the ``plugins:read`` permission. ``scope`` must be ``global`` or
    ``project`` (400 otherwise).

    Returns:
        The plugin detail, or 404 when the project or plugin is not found.
    """
    if scope not in {"global", "project"}:
        raise HTTPException(status_code=400, detail="Invalid plugin scope")
    project = await _project(request, project_id)
    views = await _service(request).list_plugins(
        project.id if project else None,
        project.path if project else ".",
    )
    view = next(
        (
            item
            for item in views
            if item.name == name and item.scope == scope
        ),
        None,
    )
    if view is None:
        raise HTTPException(status_code=404, detail="Plugin not found")
    return _serialize(view)


@router.put("/state")
async def set_plugin_state(
    body: PluginStateBody,
    request: Request,
    _=Depends(require_permission("plugins:write")),
):
    """Enable or disable a plugin for a scope.

    Requires the ``plugins:write`` permission. Scope must be ``global`` or
    ``project`` (400 otherwise), and project scope requires ``project_id`` (400
    otherwise). Unknown projects return 404; invalid plugin state changes return
    400.

    Returns:
        The updated plugin detail.
    """
    if body.scope not in {"global", "project"}:
        raise HTTPException(status_code=400, detail="Invalid plugin scope")
    if body.scope == "project" and not body.project_id:
        raise HTTPException(
            status_code=400, detail="project_id is required"
        )
    project = await _project(request, body.project_id)
    try:
        view = await _service(request).set_enabled(
            body.plugin_name,
            body.scope,
            project.id if project else None,
            body.enabled,
            project.path if project else ".",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _serialize(view)
