# Agent Skills — Design Specification

- **Date:** 2026-11-17
- **Status:** Draft (brainstormed; approved scope)
- **Sub-project:** Agent Skills — discover/activate `SKILL.md` skills (progressive disclosure), a user-level management UI, built-in skills, and `/` autocomplete.

## 1. Context and Scope

The initial spec: "When the user types a slash (`/`), a combo box autocompletes the various installed **skills** (skills are discussed later)." (`initial_spec.md:80-82`).

Agent Skills is the open format (`agentskills.io`): a skill is a folder with a required `SKILL.md` (YAML frontmatter + Markdown body) plus optional `scripts/`, `references/`, `assets/`. Agents load skills **progressively**: (1) a catalog of `name`+`description` for all skills (~50-100 tokens each), (2) the full `SKILL.md` body when activated (<5000 tokens), (3) bundled resources only on demand.

### 1.1 What this sub-project encompasses
- Filesystem discovery of skills (built-in, user, project) with precedence.
- Catalog injection + a dedicated `activate_skill` tool.
- Read-only allowlisting of skill directories for resources.
- Explicit activation via `/` autocomplete and a `skill` message field.
- A user-level Skills management UI (+ API) and a few built-in skills.

### 1.2 Boundaries
- Management UI edits **user-level** skills only (`~/.agents/skills/`); project skills are read-only in the UI (managed in the repo).
- No DB skills table; skills are folders (the standard).
- `allowed-tools` (experimental) is ignored for now.
- No context compaction exists in the harness, so "protect skill content from pruning" is moot (noted).

### 1.3 Dependencies
- `agentbox-api`; new dep `skills-ref>=0.1` (official parsing/validation/prompt XML).

## 2. Decisions and Rationale

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | Discover from standard filesystem scopes: built-in (bundled), user `~/.agents/skills/`, project `<project>/.agents/skills/`. | Matches the open standard; cross-client. |
| D2 | Precedence: **project > user > built-in** on name collisions. | Standard convention; project-specific override. |
| D3 | Use `skills-ref` (`read_properties`/`validate`/`to_prompt`). | Official reference library; compliance. |
| D4 | Catalog + behavioral instructions appended to the agent's instructions; a native `activate_skill(name)` tool. | Progressive disclosure; works for user-level skills outside the project root. |
| D5 | Allowlist skill dirs as **read-only** roots in `FilesystemToolbox`. | User chose allowlisting; lets the model read `scripts/`/`references/` without a separate tool. |
| D6 | Management UI writes **user-level** skills; guard with `agents:create` (no new permission). | Existing permission; no seed change/lockout. |
| D7 | `/` autocomplete selects a skill → message sends `skill=<name>` → explicit server-side activation. | User choice; deterministic. |

## 3. Backend

### 3.1 Skills runtime (`agentbox_api/skills.py`)
- `Skill {name, description, location: Path, scope: "builtin"|"user"|"project"}`.
- `discover_skills(project_root: str, settings) -> list[Skill]`:
  - Scan each scope dir for subdirectories containing `SKILL.md`; parse with `skills_ref.read_properties`; skip skills with no description (lenient; collect diagnostics). Max depth/bounds.
  - Dedupe by name with project > user > built-in precedence.
- `catalog_instructions(skills) -> str` = `skills_ref.to_prompt([locations])` + a short behavioral block ("When a task matches a skill's description, call `activate_skill` with its name. Relative paths in a skill resolve against its directory.").
- `augment_spec(spec, skills) -> AgentSpec`: if skills exist, return a copy with `instructions = spec.instructions + "\n\n" + catalog` and an extra `NativeToolBinding(name="activate_skill")`; else unchanged.
- `activate_skill_tool(skills)`: a callable `activate_skill(name: str)` (names constrained) returning the skill body (frontmatter stripped via `skills_ref`), the skill directory, and a listing of bundled files (one level deep, not their contents). Unknown name → error.

### 3.2 Harness
- `FilesystemToolbox(root_dir, extra_read_roots: list[Path] = [])`: reads (`read_text_file`, `read_multiple_files`, `list_directory`, `search_files`, `directory_tree`, `get_file_info`) resolve against the project root **or** any extra read root; writes stay confined to the project root.
- `runtime.build_registry(project_root, extra_read_roots=[])` registers `activate_skill` when skills are provided.

### 3.3 Session build sites
A shared helper (e.g. `skills.prepare_agent(factory, agent_name, project_root)`) returns the runtime, the skills-aware spec, the registry (with `activate_skill` + extra read roots), and the discovered skills. Used by the chat router, ACP `prompt`/`new_session`, and the A2A executor.

### 3.4 API
- `GET /skills?project_id=` (`agents:read`) → `[{name, description, scope}]` (short cache) for the UI/autocomplete. Optional `project_id` scopes project discovery.
- `GET /skills/{name}` (`agents:read`) → `{name, description, scope, body}`.
- `PUT /skills/{name}` (`agents:create`) — body `{description, body, license?, compatibility?, metadata?}` → write `~/.agents/skills/<name>/SKILL.md` (validate with `skills_ref.validate`; 422 on errors; reject invalid names).
- `DELETE /skills/{name}` (`agents:create`) — delete the **user** skill directory only (404 if not a user skill).

### 3.5 Explicit activation
`MessageRequest.skill: str | null`. When set, the backend prepends that skill's body (and directory note) as context for the turn (in addition to the catalog/`activate_skill` path).

### 3.6 Settings / built-ins
- `SKILLS_USER_DIR` (default `~/.agents/skills`).
- Bundled built-ins under `agentbox_api/skills_builtin/` (e.g. `commit-message`, `code-review`), read-only.

## 4. Frontend

- **Skills page** (`/skills`, gated by `agents:create`): table (name, description, scope badge); create/edit modal (name, description, body Markdown) for user skills; delete (user only); project/built-in shown read-only.
- **`/` autocomplete** in the composer: typing `/` lists skills (from `GET /skills`); selecting inserts `/name` and sets `skill=<name>` on the message payload. A small chip shows the selected skill.
- API helpers/hooks: `fetchSkills`, `fetchSkill`, `saveSkill`, `deleteSkill`.

## 5. Testing

- **Backend pytest** (`tests/test_skills.py`):
  - discovery + precedence (project > user > built-in) using a temp project + temp `SKILLS_USER_DIR`;
  - `skills-ref` validation (invalid frontmatter → 422);
  - `activate_skill` returns body + resource listing; unknown name errors;
  - `GET/PUT/DELETE /skills` (user upsert writes a validated `SKILL.md`; delete only user);
  - explicit `skill` injection affects the turn's prompt;
  - `FilesystemToolbox` reads resources under an extra read root but blocks writes there.
- **Frontend Vitest**: Skills page renders; `/` menu lists skills (mocked).
- **E2E**: create a user skill via the UI, then in chat type `/` and select it (asserts the composer chip / payload); the Skills page lists it.

## 6. Error Handling

- Invalid skill name/frontmatter → 422 (with `skills-ref` errors).
- Unknown skill on activation → tool error listing valid names.
- Missing `SKILL.md`/description → skipped at discovery (logged).

## 7. Open Items / Future Work

- `allowed-tools` enforcement; project-trust gating; `.claude/skills` compat; subagent-run skills; resource uploads via the UI.
- Protect skill content from compaction once the harness implements pruning.

## References

- Initial spec — `docs/initial_spec.md:80-82`.
- Agent Skills — https://agentskills.io (specification, adding-skills-support); `skills-ref` (PyPI 0.1.1).
- Existing code — `harness/tools/filesystem.py`, `agentbox_api/runtime.py`, `routers/sessions.py`, `acp_server.py`, `a2a_executor.py`, `apps/web/src/chat/Composer.tsx`.
