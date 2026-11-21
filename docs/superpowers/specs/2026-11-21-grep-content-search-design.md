# D21 - Grep Content Search Tool

- **Date:** 2026-11-21
- **Status:** Approved
- **Sub-project:** D21 - a filesystem content-search tool for Agentbox agents.
- **Source:** D21 in [`docs/ROADMAP.md`](../../ROADMAP.md), plus the OpenCode/Agentbox tool comparison that identified content search as a gap.
- **Roadmap:** `D21` in [`docs/ROADMAP.md`](../../ROADMAP.md).

## 1. Context and scope

Agentbox has `search_files`, which finds files by name or glob, but no tool for finding text inside files. Agents must read whole files or use the shell, which slows long autonomous coding sessions and increases context use.

D21 adds a bounded, line-based `grep` tool for content search.

### 1.1 In scope

- Add a `grep` filesystem read tool.
- Regex search by default and literal search via `fixed_strings`.
- Optional case-insensitive search.
- Include/exclude globs.
- Context lines, line truncation, and bounded result output.
- Safe defaults for generated/VCS directories, binary files, large files, and symlinks.
- Project-relative result paths with absolute fallback outside the project.
- Tool catalog exposure and onboarding defaults.
- Unit and registry tests.

### 1.2 Out of scope

- Multiline matching.
- PCRE features beyond Python `re`.
- `.gitignore` parsing.
- A ripgrep or external-binary dependency.
- Structured JSON output.
- New API routes, database tables, UI pages, or screenshot packs.
- Replacing `search_files`; it remains filename/glob search.

### 1.3 Dependencies

- `FilesystemToolbox` path and read-root enforcement.
- `ToolRegistry` read-tool registration.
- Tool catalog and onboarding agent defaults in the frontend.
- No new Python dependency.

## 2. Goals and success criteria

- An agent can find exact text or regex matches across project files without reading entire files.
- Results are line-addressable and reusable with `read_text_file`/`edit_file`.
- Searches are bounded in time, output size, and file count.
- Binary, oversized, generated, and symlinked content does not flood results.
- The tool is visible in the agent tools catalog and selected by default for new onboarding agents.
- Existing filename search and filesystem behavior remain unchanged.

## 3. Decisions and rationale

| # | Decision | Rationale |
|---|---|---|
| D1 | **Pure Python implementation.** | Avoids a new binary dependency and keeps behavior consistent across platforms. |
| D2 | **Regex by default; literal via `fixed_strings`.** | Matches developer expectations while keeping punctuation-heavy searches practical. |
| D3 | **One `path` argument, file or directory.** | Simple interface covering both scoped file and tree searches. |
| D4 | **Grep-style text output.** | Natural for the model and easy to correlate with file line numbers. |
| D5 | **Safe default exclusions and hard limits.** | Prevents generated directories and huge files from dominating a session. |
| D6 | **Project-relative paths, absolute fallback.** | Results are directly reusable inside the project; extra roots remain unambiguous. |
| D7 | **Catalog plus onboarding defaults, not forced bindings.** | New agents get the tool; existing agents remain explicit and unchanged. |

## 4. Tool interface

Create the public method on `FilesystemToolbox`:

```python
async def grep(
    pattern: str,
    path: str = ".",
    fixed_strings: bool = False,
    ignore_case: bool = False,
    include: list[str] | None = None,
    exclude: list[str] | None = None,
    context_lines: int = 0,
) -> str:
    ...
```

- `pattern` is required and must not be empty.
- `path` is resolved through the existing read-root checks.
- `fixed_strings=True` escapes the pattern and performs literal substring matching.
- `ignore_case=True` applies case-insensitive matching.
- `include` is an allowlist of fnmatch-style file globs.
- `exclude` adds fnmatch-style exclusions.
- `context_lines` must be between 0 and 3.
- Invalid regex raises a clear `ValueError` describing the regex error.
- No `max_results` argument; the server cap is fixed at 200.

## 5. Architecture

### 5.1 Pure scanner module

Create `packages/agentbox-harness/src/agentbox_harness/tools/grep.py`.

It owns:

- option normalization;
- regex compilation;
- file walking and filtering;
- binary/large-file detection;
- match and context collection;
- line truncation;
- result formatting and summaries.

`FilesystemToolbox.grep` performs path resolution and delegates to the scanner with the resolved read root and project root.

### 5.2 Scanner boundaries

The scanner receives:

```python
@dataclass(frozen=True)
class GrepOptions:
    pattern: str
    root: pathlib.Path
    project_root: pathlib.Path
    fixed_strings: bool
    ignore_case: bool
    include: list[str]
    exclude: list[str]
    context_lines: int
    max_results: int
    max_file_bytes: int
    max_line_chars: int
    max_walk_entries: int
```

Use named constants:

```python
MAX_GREP_RESULTS = 200
MAX_GREP_LINE_CHARS = 300
MAX_GREP_FILE_BYTES = 2 * 1024 * 1024
MAX_GREP_WALK_ENTRIES = 100_000
MAX_GREP_CONTEXT_LINES = 3
```

## 6. Scan rules

### 6.1 File selection

- Walk with `os.walk(..., followlinks=False)`.
- Never follow symlinks.
- Prune default excluded directories by name:
  - `.git`
  - `.venv`
  - `node_modules`
  - `dist`
  - `build`
  - `__pycache__`
  - `.pytest_cache`
  - `.mypy_cache`
  - `.ruff_cache`
  - `.tox`
- Apply caller `exclude` globs in addition to defaults.
- If `include` is supplied, a file must match at least one include glob.
- Include/exclude globs are relative to the search root.
- If `path` is a file, search only that file.
- Stop after the walk-entry cap and report that the walk was truncated.

### 6.2 File reading

- Skip files larger than 2 MiB and count them as skipped.
- Skip binary files when a NUL byte appears in the first 8 KiB and count them as skipped.
- Read UTF-8 with `errors="replace"`.
- Skip unreadable files and count them as skipped.
- Never read files outside the resolved read-root boundary.

### 6.3 Matching

- Split into lines and match per line.
- Regex mode uses Python `re`; literal mode uses `re.escape`.
- Default is case-sensitive; `ignore_case` adds `re.IGNORECASE`.
- Column is the 1-based character index of the first match.
- Collect at most 200 match lines.
- Context is collected from the same file only and limited to 0-3 lines before/after.
- Overlapping context ranges are merged; a line appears at most once.
- Display lines are truncated to 300 characters with a visible marker such as `…`.

## 7. Output format

- Match line: `path:line:column:text`
- Context line: `path-line-text`
- Results sorted by path and line number.
- Paths:
  - project-root-relative when the file is inside the project root;
  - absolute otherwise.
- No matches: `No matches.`
- When the match cap is reached: append `Stopped after 200 matches; narrow the path or pattern.`
- When files were skipped or the walk hit its cap, append one concise `Skipped/truncated` summary only if relevant.
- Do not print file counts or headers on ordinary successful searches.

## 8. Exposure and defaults

- Add `grep` to `TOOL_META` under `filesystem-read`, risk `read`.
- Label: `Grep content`.
- Description: search file contents, including regex/literal and include/exclude globs.
- Register with read tools and `required_flags=("read",)`, making it available in Ask and Agent modes when bound.
- Add `grep` to the onboarding wizard's default read-only tool list.
- Existing agents are unchanged; no automatic migration or forced binding.
- `search_files` remains the filename/glob search tool.

## 9. Testing

### 9.1 Scanner tests

- Simple match with correct path, line, column, and text.
- Multiple files and sorted results.
- No matches message.
- Regex versus fixed-string behavior.
- Case-sensitive versus ignore-case behavior.
- Invalid regex error.
- Include and exclude globs.
- Default generated-directory exclusions.
- Binary file skipped.
- File over 2 MiB skipped.
- Unreadable file skipped.
- Symlink not followed.
- Context lines and merged overlapping ranges.
- Line truncation at 300 characters.
- Match cap at 200.
- Walk-entry cap.
- Project-relative paths and absolute fallback for an extra read root.
- Path escape rejected before scanning.

### 9.2 Tool and UI tests

- `grep` is registered as a read tool.
- `grep` appears in Ask and Agent mode selections.
- `grep` appears in the tool catalog under filesystem read.
- Onboarding defaults include `grep`.
- Existing filename-search tests remain unchanged.

## 10. Risks and trade-offs

- **Pure Python performance:** slower than ripgrep on huge repositories. Bounded walk and file-size limits keep it predictable; a future evolution can add a fast backend behind the same interface.
- **No `.gitignore`:** generated files may be scanned unless excluded; default directory exclusions cover common cases.
- **Line-based matching:** multiline constructs are out of scope.
- **Output truncation:** long lines lose tail content, but the match location remains actionable.
- **Path privacy:** absolute paths may appear for extra roots outside the project; this is intentional for readability.

## 11. Acceptance criteria

- Agents can search file contents with regex or fixed strings.
- Results provide reusable path:line:column locations.
- Include/exclude globs and context lines work.
- Generated, binary, oversized, and symlinked content is skipped.
- Output never exceeds the configured match/line/context limits.
- The tool is visible in the catalog and included in onboarding defaults.
- Existing filesystem tools, tests, and agent behavior remain intact.
- No new dependencies, database migration, API route, or UI page are required.
