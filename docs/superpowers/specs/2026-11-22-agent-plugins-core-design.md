# Agent Plugins Core (D12a) — Design

Date: 2026-11-22
Status: Approved (design); implementation complete and verified.
Roadmap: D12a — portable Agent Plugins core (skills + MCP). D12b covers
Agentbox hook extensions.

## Goal

Load, validate, enable, and expose [Agent Plugins](https://agent-plugins.org/)
v1.0.0 packages from local user and project directories. Enabled plugins
contribute namespaced **skills** and explicitly selectable **MCP servers**.
Nothing is installed from the network, nothing is auto-executed, and plugin
hooks are deferred to D12b.

## Background

Agent Plugins v1.0.0 defines a portable package:

```text
my-plugin/
├── plugin.json       # required manifest
├── skills/           # Agent Skills, immediate child dirs with SKILL.md
└── mcp.json          # MCP server configuration
```

The standard specifies local package validation, component discovery, MCP
configuration, plugin variables, and failure isolation. Installation sources,
enablement, trust, permissions, UX, and client extensions are client-owned.

Agentbox today:

- discovers builtin/user/project skills in `agentbox_api/skills.py`;
- stores MCP bindings per agent (`McpToolBinding`) and starts them through
  `McpSessionManager`;
- has no plugin loader, no plugin enablement, and no client extension
  namespace.

## Decisions

- **Local directories only.** Discover `~/.agents/plugins` (global) and
  `<project>/.agents/plugins` (project). No network install, registry, update,
  or archive import.
- **Explicit enablement is trust.** Plugins are disabled by default. Enabling a
  plugin trusts its skills and makes its MCP servers *selectable*. Enabling
  does not auto-attach MCP servers to agents.
- **Scope follows the source.** Global plugins are enabled instance-wide;
  project plugins are enabled only for that project. No per-project override of
  a global plugin in v1.
- **Project plugin shadows global plugin when enabled.** If a project plugin and
  a global plugin share a manifest `name` and the project plugin is enabled, the
  project plugin wins and the global plugin is reported as shadowed. If the
  project plugin is disabled, the global plugin remains eligible.
- **Plugin components are sourced from the package at run time.** Agent configs
  store `PluginMcpBinding` references, not copied MCP config. A plugin update is
  reflected on the next `prepare_agent`.
- **Project-scoped plugin MCP references carry `project_id`.** Agents are
  global, so a project plugin binding resolves only when the session's project
  matches. Global plugin bindings have `project_id=None` and resolve in any
  project.
- **Plugin skills are namespaced** as `plugin-name:skill-name` in the catalog
  and `activate_skill`. Existing builtin/user/project skill names are unchanged.
- **Official schemas are vendored and validated locally.** The standard forbids
  fetching schemas during load; it does not forbid validation. Use the official
  1.0.0 `plugin.schema.json` and `mcp.schema.json` with `jsonschema`
  (Draft 2020-12), plus semantic checks.
- **Component failures are isolated.** A fatal plugin manifest rejects the whole
  plugin; an invalid skill or MCP entry is skipped; a top-level invalid
  `mcp.json` disables MCP for that plugin only.
- **D12b hooks are out of scope.** No `com.agentbox` extension directory,
  command/HTTP hook execution, argument mutation, or allow/deny in this cycle.

## Architecture

### Module layout

`packages/agentbox-api/src/agentbox_api/plugin_catalog.py`:

- `PluginManifest`, `PluginSkill`, `PluginMcpServer`, `LoadedPlugin`,
  `PluginIssue`, `PluginScope`.
- `PluginCatalog` — filesystem discovery and validation.
- Uses `skills-ref` for Agent Skills validation and `jsonschema` for manifests.

`packages/agentbox-api/src/agentbox_api/plugin_service.py`:

- `PluginService` — DB enablement state, enabled-plugin resolution, skill
  catalog contribution, and runtime MCP-reference resolution.

`packages/agentbox-api/src/agentbox_api/schemas/agent_plugins/1.0.0/`:

- `plugin.schema.json` (official, vendored)
- `mcp.schema.json` (official, vendored)
- `SOURCE.md` with canonical URLs and retrieval date.

`packages/agentbox-models/src/agentbox_models/tables/core.py`:

- `PluginState` table.

`packages/agentbox-harness/src/agentbox_harness/session.py`:

- `Session.plugin_roots` (MCP cwd/relay only).

`packages/agentbox-api/src/agentbox_api/skills.py`:

- `PreparedAgent.plugin_roots` for enabled plugin roots.

`packages/agentbox-api/src/agentbox_api/routers/plugins.py`:

- Plugin list/details/state endpoints.

Frontend:

- `apps/web/src/pages/PluginsPage.tsx`
- Agent editor plugin-MCP section
- Skills page plugin badge
- generated API types.

### Discovery

- Global root: `settings.plugins_user_dir` (default `~/.agents/plugins`).
- Project root: `<Project.path>/.agents/plugins`.
- Each immediate child directory containing `plugin.json` is one plugin. Do
  not recurse into nested plugin roots.
- Scan on demand. There is no persistent discovery cache in v1; a request loads
  the small plugin roots and caches nothing across requests.
- If the project plugin and global plugin share a `name`, the project plugin
  shadows the global plugin only when the project plugin is enabled; report a
  `warning` on the global entry when shadowed. A disabled project plugin does
  not block the global plugin.

### Manifest validation

Use the official schema with the non-fatal exceptions required by §5.2/§8.1:

1. Reject non-object JSON, missing/invalid `$schema`, or an unsupported
   `$schema` value.
2. Remove and report unknown top-level fields (warning).
3. If `extensions` exists but is not an object, remove and report it (warning).
4. Validate the normalized object against the vendored `plugin.schema.json`.
   Any remaining violation is fatal and rejects the plugin.
5. Do not validate the contents of client extension namespaces; Agentbox does
   not implement one in D12a.

The plugin root must be the filesystem-resolved plugin directory. Every
component path must resolve inside it.

### Skills discovery and validation

- Only immediate child directories under `skills/` containing a regular
  `SKILL.md` are skills; do not recurse further.
- Validate each skill with `skills-ref.validate`. Invalid skills are skipped
  and reported.
- Skill paths must resolve inside the plugin root.
- Parse name/description from `SKILL.md` frontmatter.
- Namespaced catalog name: `f"{plugin_name}:{skill_name}"`.
- If two skills inside one plugin share a name, keep the first and report a
  warning.

### MCP discovery and validation

- Only `mcp.json` at the plugin root is read; no inline MCP configuration.
- Validate the top-level object against the vendored `mcp.schema.json`:
  - invalid JSON, unsupported/mismatched `$schema`, missing/non-object
    `mcpServers`, or unknown top-level fields → disable MCP for this plugin and
    report an issue; skills continue to load.
- Validate each `mcpServers` entry independently against
  `#/$defs/server`:
  - invalid entry → skip it and report;
  - unsupported transport → skip it and report.
- Supported transports: `stdio`, `streamable-http`, `sse`.
- Semantic checks beyond the schema:
  - `command` is one token: bare executable name or `./` path inside the plugin
    root;
  - `cwd` must be `./`, `${PLUGIN_ROOT}`, or `${PLUGIN_DATA}` rooted and remain
    inside the respective root;
  - remote `url` is absolute HTTP(S), has no userinfo or fragment, and uses
    HTTPS for non-loopback hosts;
  - header names are valid and unique case-insensitively;
  - reserved env names `PLUGIN_ROOT` / `PLUGIN_DATA` are rejected;
  - expand `${PLUGIN_ROOT}` / `${PLUGIN_DATA}` only in `args`, `env`, and `cwd`.
- `PLUGIN_ROOT` is the resolved plugin directory. `PLUGIN_DATA` is
  `<settings.plugins_data_dir>/<plugin_name>`; create it before launch and
  preserve it across restarts.

### Persistence: `PluginState`

New table:

| Column | Type | Notes |
|---|---|---|
| `id` | string PK | `global:<name>` or `project:<project_id>:<name>` |
| `plugin_name` | string | manifest `name` |
| `scope` | string | `global` or `project` |
| `project_id` | string nullable | FK `project.id`, cascade delete |
| `enabled` | bool | default false |
| `created_at` | datetime | |
| `updated_at` | datetime | |

- Missing row = disabled.
- Enabling sets `enabled=true`; disabling sets it false. No separate trust flag
  in D12a; enabling is the trust action.
- A state row whose plugin is no longer discovered is ignored in v1 and is not
  shown as an orphan entry.
- Add an Alembic migration and seed the `plugins:read` / `plugins:write`
  permissions, including the admin role assignment used by the existing
  permission seed.

### Skills integration

- `Skill` gains `plugin: str | None = None`; `scope` may be `"plugin"`.
- `PluginCatalog.list_skills(project_root)` returns `Skill` entries only for
  enabled plugins.
- `discover_skills` / `prepare_agent` merge builtin, user, project, then plugin
  skills.
- `extra_read_roots` includes every enabled plugin root (and skill directories)
  for **read-only** filesystem tool access. Plugin roots are not added to the
  project write roots.
- `catalog_instructions` adds a plugin-skills block using the namespaced names;
  existing non-plugin catalog formatting is unchanged.
- `activate_skill` uses the namespaced `Skill.name`; activation reads the
  plugin skill location and resources.
- `GET /skills` includes plugin skills with `scope="plugin"` and the plugin
  source. `PUT`/`DELETE /skills/{name}` reject plugin-managed skills.
- The Skills page displays plugin skills read-only with a source badge.

### MCP integration

New model in `AgentSpec`:

```python
@dataclass(frozen=True)
class PluginMcpBinding:
    plugin: str
    server: str
    project_id: str | None = None
    id: str = ""
```

- `AgentSpec` gains `plugin_mcp_bindings: list[PluginMcpBinding] = []` as a
  separate field. Do not add it to the `ToolBinding` union.
- Stored specs keep references. `prepare_agent` receives the session project id
  and resolves each reference against the enabled plugin catalog:
  - a project-scoped reference whose `project_id` does not match the session
    project is skipped silently (the agent is valid in other projects);
  - disabled/missing plugin or missing/invalid server → log a warning and skip
    the binding; the agent still runs;
  - stdio → `McpToolBinding` with namespaced `id=f"{plugin}:{server}"`, absolute
    `command` for `./`, expanded `args`/`env`, `PLUGIN_ROOT`/`PLUGIN_DATA`, and
    the plugin root as default `cwd`;
  - remote → `McpToolBinding` with `server_url`, `transport`, and `headers`.
- Extend `McpToolBinding` with `transport: str = ""` and
  `headers: dict[str, str] = {}`. `build_mcp_toolset` maps `streamable-http` to
  `MCPToolset(url, headers=...)` and `sse` to `SSETransport(url, headers=...)`.
- `PreparedAgent` carries `plugin_roots`. Session gains a separate
  `plugin_roots` field used only by MCP cwd validation and relay:
  `Harness.prepare_mcp` passes `session.extra_roots + session.plugin_roots` to
  `McpSessionManager`, and `mcp_relay` uses the same combined list. Plugin roots
  are **not** added to `Session.extra_roots`, project write roots, ACP client
  tools, or terminal allowed roots. This gives plugin MCP servers their
  plugin-root cwd without granting filesystem/terminal write access to plugin
  packages.
- The agent MCP editor adds a **Plugin MCP servers** section:
  - global plugin servers are always listed;
  - project plugin servers are listed after the user selects a project in the
    form; selected project bindings remain visible and removable;
  - selections are stored as `PluginMcpBinding` with the matching `project_id`.
- Stale references are flagged in the editor and skipped at run time; they are
  not silently removed from the stored agent config.

### API

Permissions: `plugins:read`, `plugins:write`. Project-scoped calls follow the
same project access rules as sessions.

- `GET /plugins?project_id=…` → list of discovered global + project plugins:
  `{name, version, description, scope, project_id, enabled, skills, mcp_servers,
  issues}`.
- `PUT /plugins/state` body
  `{plugin_name, scope: "global"|"project", project_id?, enabled}` → upsert;
  validates discovery and scope.
- `GET /plugins/{scope}/{name}?project_id=…` → manifest and component details,
  including MCP server names/transports (not secrets) and issues.
- Agent create/update accepts `plugin_mcp_bindings`; validates enabled plugin,
  existing server, project scope, and unique `project_id + plugin:server` ids.
- `prepare_agent` call sites pass the session `project_id` (web, ACP, A2A, and
  subagent contexts) so project-scoped references can be matched.
- `GET /plugins` feeds the agent editor's plugin-MCP selector.

### UI

- New **Plugins** navigation page:
  - global/project filter and project selector;
  - rows with name, version, scope, enabled/disabled/invalid, skill and MCP
    counts, issue count;
  - enable/disable with a trust confirmation that explains skills/MCP
    contribution;
  - details drawer with manifest metadata, component list, and validation
    issues;
  - loading, empty, error, and retry states matching the existing UX patterns.
- Agent MCP editor:
  - **Plugin MCP servers** section grouped by plugin;
  - only enabled plugins appear;
  - selected references are removable;
  - stale references show a warning.
- Skills page:
  - plugin skills are read-only, with a source badge and no edit/delete.
- Regenerate `apps/web/openapi.json` and `apps/web/src/api/schema.d.ts`.

## Security and failure handling

- Vendored official schemas; no network schema retrieval.
- Path containment for plugin root, components, `command`, and `cwd`; reject
  symlink/junction escapes.
- Plugin roots are read-only for filesystem tools and are exposed to MCP cwd
  validation only through `Session.plugin_roots`; they must not become project
  write roots, ACP write roots, or terminal roots.
- Disabled by default; explicit trust action; only enabled plugins contribute.
- No auto-attached MCP servers. A plugin MCP server runs only if the agent
  explicitly selects it.
- No plugin hooks or arbitrary hook commands in D12a.
- Component failure boundaries exactly as specified:
  - fatal manifest → reject plugin;
  - invalid skill → skip skill;
  - invalid MCP entry → skip entry;
  - invalid top-level `mcp.json` → disable MCP, keep skills;
  - server start/connect failure → existing MCP warning path, other components
    unaffected.
- Headers/env are visible package data; no credential-reference mechanism. Do
  not log secret-looking values.
- Stale bindings are skipped and surfaced; they never fail the session.
- Plugin issues are logged with plugin/component context and shown in the UI.

## Settings

```python
plugins_user_dir: str = "~/.agents/plugins"
plugins_data_dir: str = "~/.agents/plugins/data"
```

No global enable flag: enablement is per plugin/scope. `plugins_data_dir` is
created on demand and persisted.

## Tests

### Loader/unit

- Valid minimal/full manifests; unknown top-level fields warning; non-object
  `extensions` warning; missing/invalid/unsupported `$schema`; name rules;
  non-object JSON; fatal schema violations.
- Skills: immediate-only discovery, invalid skill skipped, path escape rejected,
  duplicate skill names.
- MCP: all three transports; invalid top-level disables MCP only; invalid entry
  skipped; URL/header/path/env/placeholder rules; transport support.
- Scope shadowing: project plugin shadows global plugin.

### Service/API

- Enable/disable global and project state; persistence and timestamps.
- `plugins:read`/`plugins:write` permissions and project access.
- Discovery scopes and missing state defaults.
- Agent `plugin_mcp_bindings` validation and round-trip.
- Matching project-scoped binding resolves; mismatched project binding is
  skipped; global binding resolves in any project.
- Stale references skipped with warnings.

### Skills

- Namespaced catalog and `plugin:skill` activation.
- Plugin roots in `extra_read_roots`.
- Plugin skills read-only through the skills API/UI.
- Disabled plugins excluded.

### MCP runtime

- `PluginMcpBinding` resolves stdio and remote bindings.
- `PLUGIN_ROOT`/`PLUGIN_DATA` env and expansion.
- Plugin-root cwd accepted by `McpSessionManager` via `Session.plugin_roots`.
- Plugin roots are absent from project write roots, ACP client write paths, and
  terminal allowed roots.
- Headers and explicit transport mapping.
- Duplicate/stale ids rejected or skipped.
- MCP server start failure remains non-fatal.

### UI

- Plugins page list, project filter, enable/trust confirmation, issues, details.
- Agent plugin-MCP selector and stale-reference warning.
- Skills page read-only plugin badge.

### Migration

- `PluginState` table and `plugins:*` permission seeds apply on SQLite and the
  vendor matrix.

### E2E

- Create a temp project plugin with one valid skill and one stdio MCP server.
- Enable it, select its MCP server on an agent, start a session.
- Verify the catalog exposes `plugin:skill`, `activate_skill` works, and the MCP
  tool is available.
- Disable the plugin; verify the stale binding is skipped and the session still
  runs.

## Out of scope (D12a)

- D12b `com.agentbox` hook extensions: command/HTTP hooks, argument mutation,
  allow/deny, session/run/tool lifecycle.
- Network install/update, registries, marketplaces, signatures, sandboxing.
- Plugin-provided agents, commands, rules, LSP servers.
- Auto-attaching plugin MCP servers.
- Per-project overrides of global plugin enablement.
- Hot reload during an active run.
- Remote plugin variables/secrets beyond `${PLUGIN_ROOT}`/`${PLUGIN_DATA}`.

## References

- Agent Plugins v1.0.0: https://agent-plugins.org/specification
- Client implementation guide:
  https://agent-plugins.org/client-implementers/implement-an-agent-plugins-client
- Official schemas:
  - https://agent-plugins.org/schemas/1.0.0/plugin.schema.json
  - https://agent-plugins.org/schemas/1.0.0/mcp.schema.json
- Agent Skills: https://agentskills.io/specification
- MCP: https://modelcontextprotocol.io/specification
- Existing Agentbox surfaces:
  - `packages/agentbox-api/src/agentbox_api/skills.py`
  - `packages/agentbox-harness/src/agentbox_harness/spec.py`
  - `packages/agentbox-harness/src/agentbox_harness/tools/mcp.py`
  - `packages/agentbox-harness/src/agentbox_harness/tools/mcp_session.py`
  - `packages/agentbox-api/src/agentbox_api/routers/agents.py`
  - `apps/web/src/pages/agents/AgentMcpEditor.tsx`
  - `apps/web/src/pages/SkillsPage.tsx`
