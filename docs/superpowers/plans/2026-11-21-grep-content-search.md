# D21 Grep Content Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a bounded, pure-Python `grep` filesystem tool for regex/literal content search with safe defaults and reusable line/column results.

**Architecture:** Put the pure scanner and formatter in `agentbox_harness/tools/grep.py`; expose it through `FilesystemToolbox.grep`, register it as a read tool, and add it to the frontend tool catalog and onboarding defaults.

**Tech Stack:** Python 3.12, standard library (`re`, `os`, `fnmatch`), pytest, TypeScript/React tool catalog.

## Global Constraints

- Pure Python, no ripgrep or external binary.
- Regex by default; `fixed_strings=True` for literal search.
- Case-sensitive by default; `ignore_case=True` enables case-insensitive matching.
- One `path` argument, file or directory, default `.`.
- `include` and `exclude` are fnmatch globs relative to the search root.
- `context_lines` must be 0-3.
- Default exclusions: `.git`, `.venv`, `node_modules`, `dist`, `build`, `__pycache__`, `.pytest_cache`, `.mypy_cache`, `.ruff_cache`, `.tox`.
- Skip files over 2 MiB, binary files (NUL in first 8 KiB), and unreadable files.
- Max 200 matches, 300 characters per displayed line, 100,000 walk entries.
- Never follow symlinks.
- Match line: `path:line:column:text`; context line: `path-line-text`.
- Paths are project-relative when inside the project, otherwise absolute.
- No `.gitignore`, multiline matching, JSON output, new API routes, migration, or screenshot pack.
- `search_files` remains filename/glob search.
- Existing agents keep explicit bindings; only onboarding defaults and the catalog include `grep`.

---

### Task 1: Pure grep scanner and formatter

**Files:**
- Create: `packages/agentbox-harness/src/agentbox_harness/tools/grep.py`
- Create: `packages/agentbox-harness/tests/test_grep_tool.py`

**Interfaces:**
- Produces: `GrepOptions`, `run_grep(options: GrepOptions) -> str`, constants `MAX_GREP_RESULTS`, `MAX_GREP_LINE_CHARS`, `MAX_GREP_FILE_BYTES`, `MAX_GREP_WALK_ENTRIES`, `MAX_GREP_CONTEXT_LINES`.

- [ ] **Step 1: Write the failing scanner tests**

```python
# packages/agentbox-harness/tests/test_grep_tool.py
import pathlib

import pytest

from agentbox_harness.tools.grep import GrepOptions, run_grep


def options(root: pathlib.Path, pattern: str, **kwargs) -> GrepOptions:
    return GrepOptions(
        pattern=pattern,
        root=root,
        project_root=root,
        fixed_strings=False,
        ignore_case=False,
        include=(),
        exclude=(),
        context_lines=0,
        max_results=200,
        max_file_bytes=2 * 1024 * 1024,
        max_line_chars=300,
        max_walk_entries=100_000,
        **kwargs,
    )


def test_finds_matches_with_path_line_and_column(tmp_path: pathlib.Path):
    (tmp_path / "a.txt").write_text("first\nneedle here\n", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.txt").write_text("needle again\n", encoding="utf-8")

    out = run_grep(options(tmp_path, "needle"))

    assert "a.txt:2:1:needle here" in out
    assert "sub/b.txt:1:1:needle again" in out
    assert out.count("needle") == 2


def test_regex_and_fixed_string_modes(tmp_path: pathlib.Path):
    (tmp_path / "a.txt").write_text("foo42 foo_bar\n", encoding="utf-8")

    assert "foo42" in run_grep(options(tmp_path, r"foo\d+"))
    assert "foo42" not in run_grep(options(tmp_path, r"foo\d+", fixed_strings=True))
    assert "foo_bar" in run_grep(options(tmp_path, "foo_bar", fixed_strings=True))


def test_ignore_case_and_invalid_regex(tmp_path: pathlib.Path):
    (tmp_path / "a.txt").write_text("Needle\n", encoding="utf-8")
    assert "Needle" not in run_grep(options(tmp_path, "needle"))
    assert "Needle" in run_grep(options(tmp_path, "needle", ignore_case=True))
    with pytest.raises(ValueError, match="Invalid regex"):
        run_grep(options(tmp_path, "["))


def test_include_exclude_and_default_excludes(tmp_path: pathlib.Path):
    (tmp_path / "keep.py").write_text("hit\n", encoding="utf-8")
    (tmp_path / "skip.md").write_text("hit\n", encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "dep.js").write_text("hit\n", encoding="utf-8")

    out = run_grep(options(tmp_path, "hit", include=("*.py",)))
    assert "keep.py" in out
    assert "skip.md" not in out
    assert "node_modules" not in out


def test_context_lines_merge_and_long_lines_truncate(tmp_path: pathlib.Path):
    (tmp_path / "a.txt").write_text(
        "one\nmatch\ntwo\n" + ("x" * 400) + "\n", encoding="utf-8"
    )
    out = run_grep(options(tmp_path, "match", context_lines=2, max_line_chars=40))
    assert "a.txt-1-one" in out
    assert "a.txt:2:1:match" in out
    assert "a.txt-3-two" in out
    assert "a.txt-4-x" in out
    assert "…" in out


def test_binary_oversized_and_unreadable_files_are_skipped(tmp_path: pathlib.Path):
    (tmp_path / "binary.dat").write_bytes(b"\x00needle")
    (tmp_path / "huge.txt").write_text("needle", encoding="utf-8")
    out = run_grep(options(tmp_path, "needle", max_file_bytes=2))
    assert "No matches." in out
    assert "Skipped" in out


def test_match_and_walk_limits(tmp_path: pathlib.Path):
    for i in range(5):
        (tmp_path / f"{i}.txt").write_text("needle\n", encoding="utf-8")
    out = run_grep(options(tmp_path, "needle", max_results=2))
    assert out.count("needle") == 2
    assert "Stopped after 2 matches" in out

    walk = run_grep(options(tmp_path, "needle", max_walk_entries=1))
    assert "Search truncated" in walk


def test_project_relative_and_extra_root_absolute(tmp_path: pathlib.Path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "a.txt").write_text("needle\n", encoding="utf-8")
    out = run_grep(options(project, "needle"))
    assert "a.txt:1:1:needle" in out

    extra = tmp_path / "extra"
    extra.mkdir()
    (extra / "b.txt").write_text("needle\n", encoding="utf-8")
    out = run_grep(
        GrepOptions(
            pattern="needle",
            root=extra,
            project_root=project,
            fixed_strings=False,
            ignore_case=False,
            include=(),
            exclude=(),
            context_lines=0,
            max_results=200,
            max_file_bytes=2 * 1024 * 1024,
            max_line_chars=300,
            max_walk_entries=100_000,
        )
    )
    assert str(extra / "b.txt") in out
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```powershell
uv run pytest packages/agentbox-harness/tests/test_grep_tool.py -q
```

Expected: FAIL because `agentbox_harness.tools.grep` does not exist.

- [ ] **Step 3: Implement the scanner**

```python
# packages/agentbox-harness/src/agentbox_harness/tools/grep.py
from __future__ import annotations

import fnmatch
import os
import pathlib
import re
from dataclasses import dataclass

MAX_GREP_RESULTS = 200
MAX_GREP_LINE_CHARS = 300
MAX_GREP_FILE_BYTES = 2 * 1024 * 1024
MAX_GREP_WALK_ENTRIES = 100_000
MAX_GREP_CONTEXT_LINES = 3
DEFAULT_EXCLUDED_DIRS = {
    ".git",
    ".venv",
    "node_modules",
    "dist",
    "build",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
}


@dataclass(frozen=True)
class GrepOptions:
    pattern: str
    root: pathlib.Path
    project_root: pathlib.Path
    fixed_strings: bool = False
    ignore_case: bool = False
    include: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    context_lines: int = 0
    max_results: int = MAX_GREP_RESULTS
    max_file_bytes: int = MAX_GREP_FILE_BYTES
    max_line_chars: int = MAX_GREP_LINE_CHARS
    max_walk_entries: int = MAX_GREP_WALK_ENTRIES


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: max(limit - 1, 0)] + "…"


def _display_path(path: pathlib.Path, project_root: pathlib.Path) -> str:
    try:
        return path.resolve().relative_to(project_root.resolve()).as_posix()
    except ValueError:
        return str(path)


def _matches(rel: str, name: str, patterns: tuple[str, ...]) -> bool:
    return any(fnmatch.fnmatch(rel, p) or fnmatch.fnmatch(name, p) for p in patterns)


def _selected(path: pathlib.Path, root: pathlib.Path, options: GrepOptions) -> bool:
    rel = path.relative_to(root).as_posix()
    if options.include and not _matches(rel, path.name, options.include):
        return False
    return not _matches(rel, path.name, options.exclude)


def _iter_files(options: GrepOptions) -> tuple[list[pathlib.Path], bool]:
    if options.root.is_file():
        return [options.root], False
    files: list[pathlib.Path] = []
    visited = 0
    for dirpath, dirnames, filenames in os.walk(options.root, followlinks=False):
        dirnames[:] = sorted(
            name
            for name in dirnames
            if name not in DEFAULT_EXCLUDED_DIRS
            and not _matches(
                pathlib.Path(dirpath, name)
                .relative_to(options.root)
                .as_posix(),
                name,
                options.exclude,
            )
        )
        for name in sorted(filenames):
            visited += 1
            if visited > options.max_walk_entries:
                return files, True
            path = pathlib.Path(dirpath, name)
            if _selected(path, options.root, options):
                files.append(path)
    return files, False


def _read_lines(path: pathlib.Path, options: GrepOptions) -> list[str] | None:
    try:
        if path.stat().st_size > options.max_file_bytes:
            return None
        with path.open("rb") as handle:
            head = handle.read(8192)
            if b"\x00" in head:
                return None
            data = head + handle.read()
        return data.decode("utf-8", errors="replace").splitlines()
    except OSError:
        return None


def _format_context(text: str, options: GrepOptions) -> str:
    return _clip(text, options.max_line_chars)


def run_grep(options: GrepOptions) -> str:
    if not options.pattern.strip():
        raise ValueError("pattern must not be empty")
    if not 0 <= options.context_lines <= MAX_GREP_CONTEXT_LINES:
        raise ValueError("context_lines must be between 0 and 3")
    flags = re.IGNORECASE if options.ignore_case else 0
    source = re.escape(options.pattern) if options.fixed_strings else options.pattern
    try:
        regex = re.compile(source, flags)
    except re.error as exc:
        raise ValueError(f"Invalid regex: {exc}") from exc

    files, walk_truncated = _iter_files(options)
    matched = 0
    skipped = 0
    truncated = False
    output: list[str] = []

    for path in files:
        lines = _read_lines(path, options)
        if lines is None:
            skipped += 1
            continue
        display_path = _display_path(path, options.project_root)
        selected: dict[int, tuple[int, str] | None] = {}
        for number, line in enumerate(lines, start=1):
            if matched >= options.max_results:
                truncated = True
                break
            match = regex.search(line)
            if match is None:
                continue
            matched += 1
            selected[number] = (match.start() + 1, line)
            for context_number in range(
                max(1, number - options.context_lines),
                min(len(lines), number + options.context_lines) + 1,
            ):
                selected.setdefault(context_number, None)
        if not selected:
            continue
        for number in sorted(selected):
            value = selected[number]
            if value is None:
                output.append(
                    f"{display_path}-{number}-{_format_context(lines[number - 1], options)}"
                )
            else:
                column, line = value
                output.append(
                    f"{display_path}:{number}:{column}:{_format_context(line, options)}"
                )
        if truncated:
            break

    if not output:
        output.append("No matches.")
    if truncated:
        output.append(
            f"Stopped after {options.max_results} matches; narrow the path or pattern."
        )
    if walk_truncated:
        output.append("Search truncated after the walk-entry limit.")
    if skipped:
        output.append(f"Skipped {skipped} binary, large, or unreadable files.")
    return "\n".join(output)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run:

```powershell
uv run pytest packages/agentbox-harness/tests/test_grep_tool.py -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```powershell
git add packages/agentbox-harness/src/agentbox_harness/tools/grep.py packages/agentbox-harness/tests/test_grep_tool.py
git commit -m "feat(tools): add bounded grep scanner"
```

---

### Task 2: Expose grep through FilesystemToolbox and the tool registry

**Files:**
- Modify: `packages/agentbox-harness/src/agentbox_harness/tools/filesystem.py`
- Modify: `packages/agentbox-api/src/agentbox_api/runtime.py`
- Modify: `packages/agentbox-harness/tests/test_filesystem_tools.py`
- Create: `packages/agentbox-api/tests/test_grep_registry.py`

**Interfaces:**
- Consumes: `GrepOptions`, `run_grep`.
- Produces: `FilesystemToolbox.grep(...) -> str`; registered `grep` read tool.

- [ ] **Step 1: Write the failing tool tests**

Add to `test_filesystem_tools.py`:

```python
async def test_grep_through_filesystem_toolbox(root, tmp_path):
    box = FilesystemToolbox(root)
    await box.write_file("a.txt", "first\nneedle\n")
    await box.write_file("b.md", "needle\n")

    out = await box.grep("needle")
    assert "a.txt:2:1:needle" in out
    assert "b.md:1:1:needle" in out

    assert (await box.grep("needle", include=["*.md"])).count("needle") == 1
    assert "No matches." in await box.grep("missing")


async def test_grep_rejects_bad_context_and_path_escape(root, tmp_path):
    box = FilesystemToolbox(root)
    with pytest.raises(ValueError):
        await box.grep("x", context_lines=4)
    with pytest.raises(PathEscapesRootError):
        await box.grep("x", path="../outside")
```

Create `packages/agentbox-api/tests/test_grep_registry.py`:

```python
from agentbox_api.runtime import build_registry
from agentbox_harness.spec import Mode


def test_grep_is_registered_as_read_tool(tmp_path):
    registry = build_registry(str(tmp_path))
    names = {
        getattr(tool, "__name__", "")
        for tool in registry.select_tools(Mode(name="ask", flags={"write": False}))
    }
    assert "grep" in names
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```powershell
uv run pytest packages/agentbox-harness/tests/test_filesystem_tools.py -q
```

Expected: FAIL because `FilesystemToolbox.grep` and registry binding do not exist.

- [ ] **Step 3: Implement the toolbox method and registry entry**

In `filesystem.py`:

```python
from agentbox_harness.tools.grep import (
    MAX_GREP_CONTEXT_LINES,
    GrepOptions,
    run_grep,
)
```

Add:

```python
async def grep(
    self,
    pattern: str,
    path: str = ".",
    fixed_strings: bool = False,
    ignore_case: bool = False,
    include: list[str] | None = None,
    exclude: list[str] | None = None,
    context_lines: int = 0,
) -> str:
    if not 0 <= context_lines <= MAX_GREP_CONTEXT_LINES:
        raise ValueError("context_lines must be between 0 and 3")
    resolved = await self._resolve(path)
    options = GrepOptions(
        pattern=pattern,
        root=resolved,
        project_root=self.root_dir,
        fixed_strings=fixed_strings,
        ignore_case=ignore_case,
        include=tuple(include or ()),
        exclude=tuple(exclude or ()),
        context_lines=context_lines,
    )
    return await self._blocking(run_grep, options)
```

Register next to the other read tools in `build_registry`:

```python
("grep", box.grep),
```

- [ ] **Step 4: Run the tests to verify they pass**

Run:

```powershell
uv run pytest packages/agentbox-harness/tests/test_filesystem_tools.py -q
uv run pytest packages/agentbox-api/tests/test_grep_registry.py -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```powershell
git add packages/agentbox-harness/src/agentbox_harness/tools/filesystem.py packages/agentbox-api/src/agentbox_api/runtime.py packages/agentbox-harness/tests/test_filesystem_tools.py packages/agentbox-api/tests/test_grep_registry.py
git commit -m "feat(tools): expose grep filesystem tool"
```

---

### Task 3: Tool catalog and onboarding defaults

**Files:**
- Modify: `apps/web/src/pages/agents/toolCatalog.ts`
- Modify: `apps/web/src/pages/agents/toolCatalog.test.ts`
- Modify: `apps/web/src/onboarding/OnboardingWizard.tsx`
- Modify: `apps/web/src/onboarding/OnboardingWizard.test.tsx`

**Interfaces:**
- Produces: `grep` catalog metadata; `DEFAULT_ONBOARDING_TOOLS` including `grep`.

- [ ] **Step 1: Write the failing frontend tests**

Update `toolCatalog.test.ts`:

```ts
it("catalogs grep as a content-search read tool", () => {
  expect(TOOL_META.grep.category).toBe("filesystem-read");
  expect(TOOL_META.grep.risk).toBe("read");
  expect(TOOL_META.grep.label).toMatch(/grep/i);
});
```

Update `OnboardingWizard.test.tsx`:

```ts
import { DEFAULT_ONBOARDING_TOOLS } from "./OnboardingWizard";

test("onboarding enables grep by default", () => {
  expect(DEFAULT_ONBOARDING_TOOLS).toContain("grep");
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```powershell
cd apps/web
bun run test -- src/pages/agents/toolCatalog.test.ts src/onboarding/OnboardingWizard.test.tsx
```

Expected: FAIL because `grep` and `DEFAULT_ONBOARDING_TOOLS` are missing.

- [ ] **Step 3: Add catalog and onboarding defaults**

In `toolCatalog.ts` add:

```ts
grep: {
  name: "grep",
  label: "Grep content",
  description: "Search file contents with regex or literal text.",
  category: "filesystem-read",
  risk: "read",
},
```

In `OnboardingWizard.tsx`:

```ts
export const DEFAULT_ONBOARDING_TOOLS = [
  "read_text_file",
  "read_multiple_files",
  "list_directory",
  "search_files",
  "grep",
  "get_file_info",
];
```

Use it for the initial state:

```ts
const [agentTools, setAgentTools] = useState<string[]>(DEFAULT_ONBOARDING_TOOLS);
```

- [ ] **Step 4: Run the tests**

Run:

```powershell
cd apps/web
bun run test -- src/pages/agents/toolCatalog.test.ts src/onboarding/OnboardingWizard.test.tsx
bun run build
```

Expected: pass and typecheck.

- [ ] **Step 5: Commit**

```powershell
git add apps/web/src/pages/agents/toolCatalog.ts apps/web/src/pages/agents/toolCatalog.test.ts apps/web/src/onboarding/OnboardingWizard.tsx apps/web/src/onboarding/OnboardingWizard.test.tsx
git commit -m "feat(web): add grep to agent tool catalog"
```

---

### Task 4: Roadmap, final verification, and merge

**Files:**
- Modify: `docs/ROADMAP.md`
- Modify: `docs/superpowers/specs/2026-11-21-grep-content-search-design.md`
- Modify: `docs/superpowers/plans/2026-11-21-grep-content-search.md`

**Interfaces:**
- Produces: completed D21 evolution on `master`.

- [ ] **Step 1: Update roadmap and statuses**

- Remove D21 from the deferred backlog.
- Add history row 35: `D21 grep content search` with the spec and plan paths.
- Update the completion paragraph to include D21.
- Add `**Status:** COMPLETE` to the plan.
- Change the spec status to `Approved`.

- [ ] **Step 2: Run all checks**

```powershell
uv run pytest packages/agentbox-api -q
uv run pytest packages/agentbox-harness -q
uv run pytest packages/agentbox-models -q
uv run pytest packages/agentbox-providers -q
uv run ruff check --fix packages
uv run ty check packages
cd apps/web
bun run test
bun run build
bun run e2e
```

Expected: all pass; no migration or screenshot work.

- [ ] **Step 3: Commit docs**

```powershell
git add docs/ROADMAP.md docs/superpowers/specs/2026-11-21-grep-content-search-design.md docs/superpowers/plans/2026-11-21-grep-content-search.md
git commit -m "docs: complete D21 grep content search"
```

- [ ] **Step 4: Merge into master**

```powershell
git switch master
git merge --ff-only feat/grep-content-search
git status --short
```

Expected: fast-forward merge and clean working tree.

---

## Self-review

**Spec coverage:** Task 1 covers scanner semantics, regex/literal/case behavior, globs, context, limits, truncation, binary/large-file skipping, and project-relative paths. Task 2 exposes the tool and registers it as a read tool. Task 3 adds catalog/onboarding visibility. Task 4 covers docs, full verification, and merge.

**Placeholder scan:** No TBD/TODO steps; each task names exact files, tests, commands, and commits.

**Type consistency:** `GrepOptions`, `run_grep`, `MAX_GREP_*`, `FilesystemToolbox.grep`, `TOOL_META.grep`, and `DEFAULT_ONBOARDING_TOOLS` keep the same names across tasks.
