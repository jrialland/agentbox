# Agent Plugins Core (D12a) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

Status: Approved; implementation complete and verified.

**Goal:** Load local Agent Plugins v1.0.0 packages, validate them against the official local schemas, enable them per scope, and expose namespaced skills plus explicitly selected MCP servers.

**Architecture:** Filesystem catalog plus DB enablement. Plugin skills join the existing skill catalog as `plugin:skill`. Agents store `PluginMcpBinding` references; `prepare_agent` resolves them against the enabled plugin package at run time. Plugin roots are exposed read-only to the filesystem toolbox and separately to MCP cwd validation through `Session.plugin_roots`.

**Tech Stack:** Python 3.11+, FastAPI, SQLModel/Alembic, pydantic-ai, `skills-ref`, `jsonschema`, React 19 + Vite + Mantine.

## Global Constraints

- Python line length 100; Ruff target py311; first-party modules are `agentbox_*`.
- Do **not** commit unless the user explicitly asks.
- Validate with the vendored official Agent Plugins 1.0.0 schemas; never fetch schemas at load time.
- Plugin roots must never become project/ACP/terminal write roots. MCP cwd access uses only `Session.plugin_roots`.
- Plugins are disabled by default; enabling is the trust action.
- Plugin MCP servers never auto-attach; an agent must explicitly select them.
- D12b hooks/client extensions are out of scope.
- Backend tests: one package per invocation.
- Checks: `uv run ruff check --fix packages`, `uv run ty check packages`.

---

### Task 1: Vendor schemas and implement the plugin catalog

**Files:**
- Create: `packages/agentbox-api/src/agentbox_api/schemas/agent_plugins/1.0.0/plugin.schema.json`
- Create: `packages/agentbox-api/src/agentbox_api/schemas/agent_plugins/1.0.0/mcp.schema.json`
- Create: `packages/agentbox-api/src/agentbox_api/schemas/agent_plugins/1.0.0/SOURCE.md`
- Create: `packages/agentbox-api/src/agentbox_api/plugin_catalog.py`
- Modify: `packages/agentbox-api/pyproject.toml`
- Test: `packages/agentbox-api/tests/test_plugin_catalog.py`

**Interfaces:**
- Produces: `PluginIssue`, `PluginManifest`, `PluginSkill`, `PluginMcpServer`,
  `LoadedPlugin`, `PluginScope`.
- Produces: `PluginCatalog(user_dir, data_dir).discover(project_root, project_id) -> list[LoadedPlugin]`.
- Consumes: `skills-ref.validate`, `jsonschema.Draft202012Validator`.

- [ ] **Step 1: Vendor the official schemas**

Copy the official 1.0.0 schemas verbatim into the schema directory. Add
`SOURCE.md`:

```markdown
# Agent Plugins 1.0.0 schemas

Vendored from:
- https://agent-plugins.org/schemas/1.0.0/plugin.schema.json
- https://agent-plugins.org/schemas/1.0.0/mcp.schema.json

Retrieved: 2026-11-22. These files are validated locally; no schema is fetched
during plugin loading.
```

Add `jsonschema>=4.23` to `agentbox-api` dependencies. It is already present
transitively; make it direct.

- [ ] **Step 2: Write failing catalog tests**

```python
import json
import pathlib

import pytest

from agentbox_api.plugin_catalog import PluginCatalog


def _write_manifest(root: pathlib.Path, data: dict, name: str = "acme-tools"):
    plugin = root / name
    plugin.mkdir(parents=True)
    (plugin / "plugin.json").write_text(json.dumps(data), encoding="utf-8")
    return plugin


def test_discovers_valid_skill_and_mcp(tmp_path):
    plugin = _write_manifest(
        tmp_path,
        {
            "$schema": "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",
            "name": "acme-tools",
            "version": "1.0.0",
        },
    )
    skill = plugin / "skills" / "review"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\nname: review\ndescription: Review code\n---\n\nDo it.\n",
        encoding="utf-8",
    )
    (plugin / "mcp.json").write_text(
        json.dumps(
            {
                "$schema": "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json",
                "mcpServers": {
                    "local": {
                        "type": "stdio",
                        "command": "./bin/server",
                        "args": ["--data", "${PLUGIN_DATA}"],
                        "cwd": "${PLUGIN_ROOT}",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    (plugin / "bin").mkdir()
    (plugin / "bin" / "server").write_text("", encoding="utf-8")

    catalog = PluginCatalog(str(tmp_path), str(tmp_path / "data"))
    plugins = catalog.discover(str(tmp_path / "project"), project_id="p1")
    assert len(plugins) == 1
    loaded = plugins[0]
    assert loaded.manifest.name == "acme-tools"
    assert loaded.skills[0].scoped_name == "acme-tools:review"
    assert loaded.mcp_servers[0].transport == "stdio"
    assert not loaded.issues


def test_unknown_manifest_fields_warn_but_load(tmp_path):
    plugin = _write_manifest(
        tmp_path,
        {
            "$schema": "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",
            "name": "acme-tools",
            "unknown": True,
        },
    )
    catalog = PluginCatalog(str(tmp_path), str(tmp_path / "data"))
    loaded = catalog.discover(str(tmp_path / "project"), project_id="p1")[0]
    assert loaded.manifest.name == "acme-tools"
    assert any(issue.severity == "warning" for issue in loaded.issues)


def test_invalid_name_rejects_plugin(tmp_path):
    _write_manifest(
        tmp_path,
        {
            "$schema": "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",
            "name": "Bad_Name",
        },
    )
    catalog = PluginCatalog(str(tmp_path), str(tmp_path / "data"))
    loaded = catalog.discover(str(tmp_path / "project"), project_id="p1")[0]
    assert loaded.manifest is None
    assert any(issue.severity == "fatal" for issue in loaded.issues)
```

Add focused tests for:

- missing/unsupported `$schema` is fatal;
- non-object `extensions` is a warning and does not reject;
- path escape for `command`/component path is rejected;
- invalid skill is skipped and reported;
- invalid `mcp.json` top-level disables MCP but keeps skills;
- invalid server entry is skipped while other entries load;
- `streamable-http` and `sse` headers/URL checks;
- `${PLUGIN_ROOT}`/`${PLUGIN_DATA}` expansion only in allowed fields;
- project plugin and global plugin with the same name are both returned by the
  catalog; shadowing is resolved by `PluginService`.

- [ ] **Step 3: Run and verify failure**

Run: `uv run pytest packages/agentbox-api/tests/test_plugin_catalog.py -q --timeout=60`
Expected: FAIL (module missing).

- [ ] **Step 4: Implement the models and catalog**

```python
@dataclass(frozen=True)
class PluginIssue:
    severity: str  # fatal | warning
    component: str
    message: str


@dataclass(frozen=True)
class PluginManifest:
    schema: str
    name: str
    version: str
    description: str
    author: dict
    homepage: str
    repository: str
    license: str
    keywords: tuple[str, ...]
    extensions: dict
    root: pathlib.Path


@dataclass(frozen=True)
class PluginSkill:
    name: str
    description: str
    location: pathlib.Path
    plugin_name: str

    @property
    def scoped_name(self) -> str:
        return f"{self.plugin_name}:{self.name}"


@dataclass(frozen=True)
class PluginMcpServer:
    name: str
    transport: str
    command: str = ""
    args: tuple[str, ...] = ()
    env: dict[str, str] = field(default_factory=dict)
    cwd: str = ""
    url: str = ""
    headers: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class LoadedPlugin:
    manifest: PluginManifest | None
    root: pathlib.Path
    scope: str
    project_id: str | None
    skills: tuple[PluginSkill, ...] = ()
    mcp_servers: tuple[PluginMcpServer, ...] = ()
    issues: tuple[PluginIssue, ...] = ()
```

Load schemas with `importlib.resources.files("agentbox_api.schemas..." )` or
`pathlib.Path(__file__).parent / "schemas"`. Use
`jsonschema.Draft202012Validator`.

Manifest validation:

```python
KNOWN_FIELDS = {
    "$schema", "name", "version", "description", "author", "homepage",
    "repository", "license", "keywords", "extensions",
}
SUPPORTED_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"

def _validate_manifest(raw: dict, root: pathlib.Path):
    issues = []
    if not isinstance(raw, dict):
        return None, [PluginIssue("fatal", "manifest", "plugin.json must be an object")]
    if raw.get("$schema") != SUPPORTED_SCHEMA:
        return None, [PluginIssue("fatal", "manifest", "unsupported or missing $schema")]
    normalized = {}
    for key, value in raw.items():
        if key not in KNOWN_FIELDS:
            issues.append(PluginIssue("warning", "manifest", f"unknown field {key!r}"))
            continue
        normalized[key] = value
    if not isinstance(normalized.get("extensions", {}), dict):
        issues.append(PluginIssue("warning", "manifest", "extensions must be an object"))
        normalized.pop("extensions", None)
    errors = sorted(_manifest_validator.iter_errors(normalized), key=str)
    if errors:
        issues.append(PluginIssue("fatal", "manifest", errors[0].message))
        return None, issues
    return normalized, issues
```

Reject the plugin if `manifest` is `None`. Parse `PluginManifest` from the
validated object.

Skills:

```python
def _load_skills(root, plugin_name, issues):
    skills_dir = root / "skills"
    if not skills_dir.exists():
        return ()
    if not skills_dir.is_dir():
        issues.append(PluginIssue("warning", "skills", "skills is not a directory"))
        return ()
    result = []
    seen = set()
    for entry in sorted(skills_dir.iterdir()):
        skill_md = entry / "SKILL.md"
        if not entry.is_dir() or not skill_md.is_file():
            continue
        try:
            _ensure_inside(root, skill_md)
            errors = validate(entry)
        except Exception as exc:
            issues.append(PluginIssue("warning", f"skill:{entry.name}", str(exc)))
            continue
        if errors:
            issues.append(PluginIssue("warning", f"skill:{entry.name}", "; ".join(map(str, errors))))
            continue
        props = read_properties(entry)
        if props.name in seen:
            issues.append(PluginIssue("warning", f"skill:{props.name}", "duplicate skill name"))
            continue
        seen.add(props.name)
        result.append(PluginSkill(props.name, props.description, skill_md, plugin_name))
    return tuple(result)
```

MCP:

```python
def _load_mcp(root, data_dir, issues):
    path = root / "mcp.json"
    if not path.exists():
        return ()
    if not path.is_file():
        issues.append(PluginIssue("warning", "mcp", "mcp.json is not a file"))
        return ()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        issues.append(PluginIssue("warning", "mcp", f"invalid mcp.json: {exc}"))
        return ()
    errors = sorted(_mcp_validator.iter_errors(raw), key=str)
    if errors:
        issues.append(PluginIssue("warning", "mcp", errors[0].message))
        return ()
    servers = []
    for name, entry in raw["mcpServers"].items():
        entry_errors = sorted(
            _mcp_server_validator.iter_errors(entry), key=str
        )
        if entry_errors:
            issues.append(PluginIssue("warning", f"mcp:{name}", entry_errors[0].message))
            continue
        try:
            servers.append(_build_mcp_server(name, entry, root, data_dir))
        except ValueError as exc:
            issues.append(PluginIssue("warning", f"mcp:{name}", str(exc)))
    return tuple(servers)
```

`_build_mcp_server` performs semantic checks:

- `command`: bare or `./`; resolve `./` inside root.
- `cwd`: expand placeholders, validate containment in root or data dir.
- remote URL: parse, reject userinfo/fragment, require HTTPS for non-loopback.
- headers: duplicate case-insensitive names rejected.
- env: reserved names rejected; expand `${PLUGIN_ROOT}`/`${PLUGIN_DATA}`.
- args: expand placeholders.

Path helper:

```python
def _ensure_inside(root: pathlib.Path, target: pathlib.Path) -> pathlib.Path:
    resolved = target.resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError(f"path escapes plugin root: {target}")
    return resolved
```

Catalog discovery:

```python
def discover(self, project_root, project_id):
    plugins = []
    plugins.extend(self._scan(self.user_dir, "global", None))
    plugins.extend(self._scan(pathlib.Path(project_root) / ".agents" / "plugins", "project", project_id))
    return plugins
```

`_scan` iterates immediate child directories with `plugin.json`; catches
exceptions and returns a `LoadedPlugin(manifest=None, ..., issues=[fatal])` for
unexpected failures.

- [ ] **Step 5: Run catalog tests**

Run: `uv run pytest packages/agentbox-api/tests/test_plugin_catalog.py -q --timeout=60`
Expected: PASS.

---

### Task 2: Add `PluginState`, migration, and permissions

**Files:**
- Modify: `packages/agentbox-models/src/agentbox_models/tables/core.py`
- Create: `packages/agentbox-models/alembic/versions/<newrev>_plugin_state.py`
- Modify: `packages/agentbox-api/src/agentbox_api/dev_seed.py`
- Test: `packages/agentbox-models/tests/test_plugin_state.py` (or API service tests)

**Interfaces:**
- Produces: `PluginState(id, plugin_name, scope, project_id, enabled, created_at, updated_at)`.
- Produces permissions `plugins:read`, `plugins:write` in `ALL_PERMISSIONS`.

- [ ] **Step 1: Write a failing model/migration test**

Prefer an API service test that inserts and queries `PluginState` after
`init_db`; the models package does not run Alembic in unit tests. Create a
small test in `packages/agentbox-api/tests/test_plugin_state.py`:

```python
from agentbox_models.db import create_engine_and_sessionmaker, init_db
from agentbox_models.tables.core import PluginState


async def test_plugin_state_round_trip(tmp_path):
    engine, factory = create_engine_and_sessionmaker(
        "sqlite+aiosqlite:///:memory:"
    )
    await init_db(engine)
    try:
        async with factory() as s:
            s.add(PluginState(id="global:acme", plugin_name="acme", scope="global"))
            await s.commit()
        async with factory() as s:
            row = await s.get(PluginState, "global:acme")
            assert row is not None and row.enabled is False
    finally:
        await engine.dispose()
```

- [ ] **Step 2: Run and verify failure**

Run: `uv run pytest packages/agentbox-api/tests/test_plugin_state.py -q --timeout=60`
Expected: FAIL (`PluginState` missing).

- [ ] **Step 3: Implement the table**

```python
class PluginState(SQLModel, table=True):
    id: str = Field(primary_key=True, max_length=160)
    plugin_name: str = Field(max_length=64)
    scope: str = Field(max_length=16)
    project_id: str | None = Field(
        default=None, foreign_key="project.id", ondelete="CASCADE"
    )
    enabled: bool = False
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
```

Match the existing `utcnow`/datetime conventions in `core.py`.

- [ ] **Step 4: Add the migration**

Create a new Alembic revision with `down_revision = "cb4176fc9480"`. In
`upgrade()`:

- `op.create_table("pluginstate", ...)` with the columns above and FK cascade.
- Insert `plugins:read` and `plugins:write` permissions with fixed string ids
  (`plugins_read`, `plugins_write`).
- If an `admin` role exists, insert `rolepermissionlink` rows for those ids.
- In `downgrade()`, delete the permission/link rows and drop the table.

Use `op.get_bind()` and `sa.text()` with bind parameters. Keep the migration
safe when the admin role is absent.

- [ ] **Step 5: Seed dev permissions**

Add `"plugins:read"` and `"plugins:write"` to `ALL_PERMISSIONS` in
`dev_seed.py`.

- [ ] **Step 6: Run the test**

Run: `uv run pytest packages/agentbox-api/tests/test_plugin_state.py -q --timeout=60`
Expected: PASS.

---

### Task 3: Implement `PluginService`

**Files:**
- Create: `packages/agentbox-api/src/agentbox_api/plugin_service.py`
- Test: `packages/agentbox-api/tests/test_plugin_service.py`

**Interfaces:**
- Produces: `PluginView`, `ResolvedPluginMcp`.
- Produces:
  - `PluginService(factory, user_dir, data_dir)`
  - `await list_plugins(project_id, project_root) -> list[PluginView]`
  - `await set_enabled(plugin_name, scope, project_id, enabled) -> PluginView`
  - `await enabled_plugins(project_id, project_root) -> list[LoadedPlugin]`
  - `await list_plugin_skills(project_id, project_root) -> list[PluginSkill]`
  - `await plugin_roots(project_id, project_root) -> list[pathlib.Path]`
  - `await resolve_mcp(plugin_name, server_name, project_id, project_root) -> ResolvedPluginMcp | None`

- [ ] **Step 1: Write failing service tests**

```python
async def test_enable_global_plugin_and_resolve_skill(tmp_path):
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    try:
        _write_plugin(tmp_path / "plugins", "acme-tools")
        service = PluginService(factory, str(tmp_path / "plugins"), str(tmp_path / "data"))
        await service.set_enabled("acme-tools", "global", None, True)
        skills = await service.list_plugin_skills(None, str(tmp_path / "project"))
        assert skills[0].scoped_name == "acme-tools:review"
    finally:
        await engine.dispose()
```

Add tests for:

- project enablement scoped to one project;
- disabled plugin contributes no skills/MCP;
- project plugin shadows a global plugin only when enabled;
- stale `PluginState` row for a missing plugin is ignored;
- `resolve_mcp` returns expanded env/cwd and headers;
- `plugin_roots` returns enabled plugin roots only.

- [ ] **Step 2: Run and verify failure**

Run: `uv run pytest packages/agentbox-api/tests/test_plugin_service.py -q --timeout=60`
Expected: FAIL.

- [ ] **Step 3: Add settings**

Add to `packages/agentbox-api/src/agentbox_api/config.py`:

```python
plugins_user_dir: str = "~/.agents/plugins"
plugins_data_dir: str = "~/.agents/plugins/data"
```

- [ ] **Step 4: Implement**

`PluginState` IDs:

```python
def _state_id(plugin_name: str, scope: str, project_id: str | None) -> str:
    if scope == "global":
        return f"global:{plugin_name}"
    return f"project:{project_id}:{plugin_name}"
```

`enabled_plugins`:

```python
async def enabled_plugins(self, project_id, project_root):
    catalog = PluginCatalog(self.user_dir, self.data_dir)
    discovered = catalog.discover(project_root, project_id)
    async with self.factory() as s:
        rows = (await s.execute(select(PluginState))).scalars().all()
    enabled_ids = {row.id for row in rows if row.enabled}
    by_name = {}
    for plugin in discovered:
        key = plugin.manifest.name if plugin.manifest else None
        if key is None:
            continue
        if plugin.scope == "project" and _state_id(key, "project", project_id) in enabled_ids:
            by_name[key] = plugin
        elif key not in by_name and _state_id(key, "global", None) in enabled_ids:
            by_name[key] = plugin
    return list(by_name.values())
```

This encodes project-first shadowing: a project plugin replaces a global of
the same name only when enabled; otherwise the global remains.

`list_plugin_skills` flattens `plugin.skills` from `enabled_plugins`.

`plugin_roots` returns `[plugin.root for plugin in enabled_plugins(...)]`.

`set_enabled`:

- Validate plugin discovery for the requested scope/project.
- Upsert `PluginState` by `_state_id`.
- Update `updated_at`.
- Return a `PluginView`.

`resolve_mcp`:

- Resolve the enabled plugin with the matching scope/project.
- Find the server by name.
- Return:
  - `command`: absolute path if `./`, else bare;
  - `args`/`env` already expanded by the catalog (catalog can store expanded
    args/env; or service expands with `PLUGIN_ROOT`/`PLUGIN_DATA`);
  - `cwd`: absolute plugin root or expanded configured path;
  - `url`/`headers`/`transport`.
- Create `<plugins_data_dir>/<plugin_name>` before returning.

`PluginView` fields: `name`, `version`, `description`, `scope`, `project_id`,
`enabled`, `valid`, `skills`, `mcp_servers`, `issues`. `skills`/`mcp_servers`
are summaries (names/transports), not full bodies.

- [ ] **Step 5: Run service tests**

Run: `uv run pytest packages/agentbox-api/tests/test_plugin_service.py -q --timeout=60`
Expected: PASS.

---

### Task 4: Integrate plugin skills

**Files:**
- Modify: `packages/agentbox-api/src/agentbox_api/skills.py`
- Modify: `packages/agentbox-api/src/agentbox_api/routers/skills.py`
- Test: `packages/agentbox-api/tests/test_skills.py`
- Test: `packages/agentbox-api/tests/test_plugin_skills.py`

**Interfaces:**
- `Skill` gains `plugin: str | None = None`.
- `discover_skills(project_root, user_dir, extra_skills=None)`.
- `PreparedAgent` gains `plugin_roots: list[pathlib.Path]`.
- `prepare_agent` gains `project_id`, `plugins_user_dir`, `plugins_data_dir`.

- [ ] **Step 1: Write failing tests**

```python
async def test_plugin_skill_is_namespaced_and_read_only(tmp_path, client, admin):
    _write_plugin(tmp_path / "plugins", "acme-tools")
    await enable_plugin(admin, "acme-tools", "global")
    response = await client.get("/skills")
    assert any(s["name"] == "acme-tools:review" for s in response.json())
    put = await client.put("/skills/acme-tools:review", json={"description": "x", "body": "x"})
    assert put.status_code == 400
```

Also assert `prepare_agent` returns a `Skill` with `scope="plugin"` and that
`extra_read_roots` includes the plugin root.

- [ ] **Step 2: Run and verify failure**

Run: `uv run pytest packages/agentbox-api/tests/test_plugin_skills.py -q --timeout=60`
Expected: FAIL.

- [ ] **Step 3: Implement**

- Extend `Skill`:

```python
@dataclass
class Skill:
    name: str
    description: str
    location: pathlib.Path
    scope: str
    plugin: str | None = None
```

- `discover_skills(project_root, user_dir, extra_skills=None)` merges builtin,
  user, project, then `extra_skills`; namespaced plugin names avoid collisions.
- `prepare_agent` constructs a `PluginService` when `plugins_user_dir` and
  `plugins_data_dir` are provided, maps `PluginSkill` to `Skill`, and passes
  `extra_skills` to `discover_skills`.
- `extra_read_roots` includes `[s.location.parent for s in skills]` and enabled
  plugin roots.
- `catalog_instructions` appends:

```text
Plugin-provided skills (activate by their full namespaced name):
- acme-tools:review — Review code
```

- `PreparedAgent` stores `plugin_roots`; all call sites that create `Session`
  pass `plugin_roots=prepared.plugin_roots`.
- `routers/skills.py` builds plugin skills via `PluginService` and includes
  `plugin` in responses. `PUT`/`DELETE` reject names containing `:` and
  `scope="plugin"`.

- [ ] **Step 4: Run skills tests**

Run: `uv run pytest packages/agentbox-api/tests/test_skills.py packages/agentbox-api/tests/test_plugin_skills.py -q --timeout=60`
Expected: PASS.

---

### Task 5: Integrate plugin MCP bindings and runtime roots

**Files:**
- Modify: `packages/agentbox-harness/src/agentbox_harness/spec.py`
- Modify: `packages/agentbox-harness/src/agentbox_harness/tools/mcp.py`
- Modify: `packages/agentbox-harness/src/agentbox_harness/session.py`
- Modify: `packages/agentbox-harness/src/agentbox_harness/harness.py`
- Modify: `packages/agentbox-api/src/agentbox_api/skills.py`
- Modify: `packages/agentbox-api/src/agentbox_api/routers/agents.py`
- Modify: `packages/agentbox-api/src/agentbox_api/routers/sessions.py`
- Modify: `packages/agentbox-api/src/agentbox_api/acp_server.py`
- Modify: `packages/agentbox-api/src/agentbox_api/a2a_executor.py`
- Modify: `packages/agentbox-api/src/agentbox_api/subagent_sessions.py`
- Test: `packages/agentbox-harness/tests/test_plugin_mcp.py`
- Test: `packages/agentbox-api/tests/test_plugin_mcp_wiring.py`

**Interfaces:**
- `PluginMcpBinding(plugin, server, project_id=None, id="")`.
- `AgentSpec.plugin_mcp_bindings: list[PluginMcpBinding]`.
- `McpToolBinding.transport: str = ""`, `McpToolBinding.headers: dict[str, str] = {}`.
- `Session.plugin_roots: list[str]`.
- `PreparedAgent.plugin_roots`.

- [ ] **Step 1: Write failing harness tests**

```python
def test_mcp_binding_round_trips_plugin_reference():
    spec = AgentSpec(
        name="coder",
        description="d",
        instructions="i",
        tool_bindings=[],
        plugin_mcp_bindings=[
            PluginMcpBinding(plugin="acme-tools", server="local", project_id="p1")
        ],
        model_binding=ModelBinding(model="test", provider="test"),
    )
    dumped = spec.model_dump()
    assert dumped["plugin_mcp_bindings"][0]["project_id"] == "p1"
    assert AgentSpec.model_validate(dumped).plugin_mcp_bindings[0].plugin == "acme-tools"


async def test_build_mcp_toolset_uses_sse_transport():
    binding = McpToolBinding(
        id="acme-tools:local",
        server_url="https://example.test/sse",
        transport="sse",
        headers={"X-Tenant": "public"},
    )
    toolset = build_mcp_toolset(binding)
    assert toolset.id == "acme-tools:local"
```

- [ ] **Step 2: Run and verify failure**

Run: `uv run pytest packages/agentbox-harness/tests/test_plugin_mcp.py -q --timeout=60`
Expected: FAIL.

- [ ] **Step 3: Implement the models and runtime**

`spec.py`:

```python
@dataclass(frozen=True)
class PluginMcpBinding:
    plugin: str
    server: str
    project_id: str | None = None
    id: str = ""
```

Add `plugin_mcp_bindings: list[PluginMcpBinding] = field(default_factory=list)`
to `AgentSpec`; ensure `ToolBinding` stays unchanged.

`McpToolBinding` gains:

```python
transport: str = ""
headers: dict[str, str] = field(default_factory=dict)
```

`tools/mcp.py`:

```python
from fastmcp.client.transports import SSETransport, StdioTransport

def build_mcp_toolset(binding, *, cwd=None):
    if binding.command:
        ...
    headers = binding.headers or None
    if binding.transport == "sse":
        return MCPToolset(
            SSETransport(binding.server_url, headers=headers),
            id=mcp_toolset_id(binding),
        )
    return MCPToolset(
        binding.server_url,
        id=mcp_toolset_id(binding),
        headers=headers,
    )
```

Verify the fastmcp transport signatures; adjust if `SSETransport` expects a
different header argument.

`session.py` adds `plugin_roots: list[str] = field(default_factory=list)`.

`harness.py` `prepare_mcp`:

```python
roots = [*session.extra_roots, *session.plugin_roots]
return await self.mcp_manager.toolsets_for(
    session.session_id, bindings, session.project_root, roots
)
```

`skills.py` `prepare_agent`:

- Resolve each `PluginMcpBinding` whose `project_id` is `None` or equals the
  session project id.
- Convert resolved entries to `McpToolBinding` and append to the run-time
  `spec.tool_bindings` via `spec.model_copy(update={"tool_bindings": [...]})`.
- Collect `plugin_roots`.
- Pass `project_id` to `PluginService`; skip mismatched project bindings
  silently.
- Add `plugin_roots` to `PreparedAgent`.
- Add `project_id`, `plugins_user_dir`, and `plugins_data_dir` to
  `SubagentSessionContext` and pass them into the child `prepare_agent` call.

`routers/agents.py`:

- Add `plugin_mcp_bindings` to the create/update request model.
- Validate via `PluginService.resolve_mcp`: plugin enabled, server exists,
  project scope valid, unique `(project_id, plugin, server)`.
- Store in `AgentSpec`.

Session construction sites:

- Add `project_id` to `prepare_agent` calls (web project row, ACP project,
  A2A project, subagent context project id).
- Pass `plugins_user_dir=settings.plugins_user_dir` and
  `plugins_data_dir=settings.plugins_data_dir` from each caller.
- Add `plugin_roots=prepared.plugin_roots` to `Session(...)`.
- Update `_agent_spec_and_root` / session loading to return the project id and
  resolve plugin roots for `mcp_relay`; pass
  `extra_roots + plugin_roots` to relay calls.

- [ ] **Step 4: Run MCP tests**

Run: `uv run pytest packages/agentbox-harness/tests/test_plugin_mcp.py packages/agentbox-api/tests/test_plugin_mcp_wiring.py -q --timeout=60`
Expected: PASS.

---

### Task 6: Add the plugins API

**Files:**
- Create: `packages/agentbox-api/src/agentbox_api/routers/plugins.py`
- Modify: `packages/agentbox-api/src/agentbox_api/app.py`
- Test: `packages/agentbox-api/tests/test_plugins_router.py`

**Interfaces:**
- `GET /plugins?project_id=…` (`plugins:read`)
- `GET /plugins/{scope}/{name}?project_id=…` (`plugins:read`)
- `PUT /plugins/state` (`plugins:write`)

- [ ] **Step 1: Write failing router tests**

```python
async def test_list_plugins_returns_scope_and_state(client, admin, plugin_fixture):
    response = await client.get("/plugins?project_id=p1", headers=admin)
    assert response.status_code == 200
    plugin = response.json()[0]
    assert plugin["scope"] in {"global", "project"}
    assert "issues" in plugin


async def test_enable_plugin_requires_write_permission(client, reader, plugin_fixture):
    response = await client.put(
        "/plugins/state",
        json={"plugin_name": "acme-tools", "scope": "global", "enabled": True},
        headers=reader,
    )
    assert response.status_code == 403
```

Add tests for project access, invalid scope, unknown plugin, shadowing, and
issues.

- [ ] **Step 2: Run and verify failure**

Run: `uv run pytest packages/agentbox-api/tests/test_plugins_router.py -q --timeout=60`
Expected: FAIL.

- [ ] **Step 3: Implement**

- `router = APIRouter(prefix="/plugins", tags=["plugins"])`.
- Build `PluginService(request.app.state.session_factory, settings.plugins_user_dir, settings.plugins_data_dir)`.
- `GET /plugins`:
  - Resolve project root from `Project` if `project_id` is provided; 404 if
    missing.
  - Return `service.list_plugins(project_id, project_root)` serialized.
- `GET /plugins/{scope}/{name}`:
  - Validate `scope`; resolve project root; return details or 404.
- `PUT /plugins/state`:
  - Validate scope/project; upsert; return the updated view.
- Register `plugins_router` in `app.py`.
- Add permission descriptions if the UI needs them.

- [ ] **Step 4: Run router tests**

Run: `uv run pytest packages/agentbox-api/tests/test_plugins_router.py -q --timeout=60`
Expected: PASS.

---

### Task 7: Frontend Plugins page, nav, and API client

**Files:**
- Create: `apps/web/src/pages/PluginsPage.tsx`
- Create: `apps/web/src/pages/PluginsPage.test.tsx`
- Modify: `apps/web/src/App.tsx`
- Modify: `apps/web/src/design-system/shell/CommandShell.tsx`
- Modify: `apps/web/src/api/endpoints.ts`
- Modify: `apps/web/src/api/queries.ts`
- Modify: `apps/web/src/pages/admin/permissionDescriptions.ts`
- Test: `apps/web/src/pages/PluginsPage.test.tsx`

**Interfaces:**
- Types: `PluginInfo`, `PluginComponentSummary`, `PluginIssue`, `PluginStateUpdate`.
- Endpoints: `fetchPlugins(projectId?)`, `fetchPlugin(scope, name, projectId?)`, `setPluginState(body)`.
- Queries: `usePlugins(projectId?)`, `useSetPluginState()`.

- [ ] **Step 1: Write a failing page test**

```tsx
test("lists plugins and enables one after trust confirmation", async () => {
  vi.spyOn(endpoints, "fetchPlugins").mockResolvedValue([
    {
      name: "acme-tools",
      version: "1.0.0",
      description: "Tools",
      scope: "global",
      project_id: null,
      enabled: false,
      skills: ["review"],
      mcp_servers: ["local"],
      issues: [],
    },
  ]);
  renderPage();
  expect(await screen.findByText("acme-tools")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Enable" }));
  expect(screen.getByText(/trust/i)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Enable and trust" }));
  await waitFor(() => expect(setPluginState).toHaveBeenCalled());
});
```

- [ ] **Step 2: Run and verify failure**

Run: `cd apps/web && bun run test -- PluginsPage`
Expected: FAIL.

- [ ] **Step 3: Implement the page**

- Use `PageContainer`/`AdminTablePage` patterns.
- Project selector via `useProjects()`; global plugins always listed, project
  plugins loaded for the selected project.
- Table rows with name, version, scope, enabled/disabled/invalid, component
  counts, issues.
- Enable/disable modal with trust copy; call `useSetPluginState`.
- Details drawer listing manifest metadata, skills, MCP servers, issues.
- Empty/loading/error/retry states.
- Add nav item `{ to: "/plugins", label: "Plugins", icon: RiPlugLine, permission: "plugins:read" }`
  and route.
- Add permission description for `plugins:read`/`plugins:write` if the admin
  permission list needs it.
- API client functions and query hooks; invalidate `["plugins"]` after state
  changes.

- [ ] **Step 4: Run page tests**

Run: `cd apps/web && bun run test -- PluginsPage`
Expected: PASS.

---

### Task 8: Agent plugin-MCP selector and Skills page badge

**Files:**
- Modify: `apps/web/src/pages/agents/mcpTypes.ts`
- Modify: `apps/web/src/pages/agents/AgentMcpEditor.tsx`
- Modify: `apps/web/src/pages/agents/AgentFormDrawer.tsx`
- Modify: `apps/web/src/pages/SkillsPage.tsx`
- Test: `apps/web/src/pages/agents/AgentMcpEditor.test.tsx`
- Test: `apps/web/src/pages/SkillsPage.test.tsx`

**Interfaces:**
- `PluginMcpDraft` or a separate `pluginMcpServers` list in the agent form.
- Plugin bindings serialize as `{plugin, server, project_id, id}`.

- [ ] **Step 1: Write failing editor tests**

```tsx
test("shows global plugin MCP servers and stores a plugin binding", async () => {
  renderEditor({ plugins: [globalPlugin] });
  expect(await screen.findByText("acme-tools / local")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("checkbox", { name: /acme-tools \/ local/ }));
  expect(onChange).toHaveBeenCalledWith(
    expect.arrayContaining([
      expect.objectContaining({ plugin: "acme-tools", server: "local", project_id: null }),
    ]),
  );
});

test("project plugin servers require a selected project", async () => {
  renderEditor({ plugins: [projectPlugin], projectId: null });
  expect(screen.queryByText("project-tools / local")).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run and verify failure**

Run: `cd apps/web && bun run test -- AgentMcpEditor`
Expected: FAIL.

- [ ] **Step 3: Implement**

- Fetch plugins via `usePlugins(projectId)` in `AgentFormDrawer`.
- Add a project selector in the plugin-MCP section for project plugin servers.
- Render global plugin servers always; project plugin servers only when a
  project is selected.
- Selected plugin bindings appear in a separate list with a source label and
  remove action; stale selections show a warning.
- Do not expose plugin headers/secrets in the form.
- Skills page: show a `plugin` badge and hide edit/delete for plugin skills.

- [ ] **Step 4: Run editor/skills tests**

Run: `cd apps/web && bun run test -- AgentMcpEditor SkillsPage`
Expected: PASS.

---

### Task 9: OpenAPI, E2E, and full verification

- [ ] **Step 1: Regenerate API artifacts**

```powershell
uv run python apps/web/scripts/gen-openapi.py
cd apps/web
bun run codegen
```

If codegen dependencies are unavailable, stop and report; do not hand-edit
`schema.d.ts`.

- [ ] **Step 2: Add an API/integration E2E test**

Create a temp project plugin with one valid skill and one stdio MCP server.
Enable it, save an agent with the plugin MCP binding, run a session, and assert:

- the skill catalog contains `plugin:skill`;
- `activate_skill` returns the body;
- the plugin MCP toolset is available;
- disabling the plugin causes the stale binding to be skipped without failing
  the session.

Use the existing fake/stdio MCP test server if available; otherwise add a tiny
stdio MCP fixture.

- [ ] **Step 3: Run checks and tests**

```powershell
uv run ruff check --fix packages
uv run ty check packages
uv run pytest packages/agentbox-harness -q
uv run pytest packages/agentbox-api -q
uv run pytest packages/agentbox-models -q
uv run pytest packages/agentbox-providers -q
cd apps/web
bun run test
bun run build
```

Expected: clean checks; tests pass or skip.

- [ ] **Step 4: Update ROADMAP**

Add sub-project 44 (D12a) with the spec/plan paths, and note that D12b remains
deferred.
