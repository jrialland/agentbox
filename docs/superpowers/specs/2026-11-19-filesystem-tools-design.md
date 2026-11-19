# File System Tools — Design

Date: 2026-11-19
Status: Approved (design), spec awaiting review.

## Goal

Replace the current 3-tool filesystem layer with a solid, reference-faithful
toolset modelled on `@modelcontextprotocol/server-filesystem`, and add three
extensions:

1. A guarded `delete_path` (upstream advertises directory deletion but the
   current tool list has no delete tool).
2. An image-optimizing `read_media_file` that passes images to the model as
   real image content after downscaling/recompressing to PNG.
3. A post-tool hook mechanism so future enrichments (e.g. language-server
   diagnostics after `write_file`) can append information to tool results
   without changing tool signatures.

## Principles

- **Full behavioural parity** with the reference tool names, inputs, and
  semantics (where the reference has a delete tool, use the guarded version
  below).
- **Basic containment**: paths are resolved and confined to the project root
  (writes) or project root + read-only roots (reads). No Windows-specific
  reserved-name / ADS guards in this iteration.
- Native tools remain **opt-in per agent**; an empty `tool_bindings` list means
  no native tools (existing behaviour preserved).
- Every mutating tool carries the `write` mode flag, so Ask mode disables all
  of them.

## Tool surface

Registered by `agentbox_api.runtime.build_registry`.

### Read tools (`required_flags=("read",)`)

| Tool | Inputs | Behaviour |
|---|---|---|
| `read_text_file` | `path`, `head?`, `tail?` | UTF-8; `head`/`tail` mutually exclusive; `0` returns no lines; refuses non-regular files |
| `read_file` | `path` | Deprecated alias of `read_text_file` |
| `read_media_file` | `path` | Images: Pillow pipeline (see below) → `ToolReturn(summary, content=[BinaryContent(image/png)])`; audio/PDF/other binary → `BinaryContent` with detected MIME; undecodable image → error |
| `read_multiple_files` | `paths[]` | `--- path ---` sections; failed reads reported, batch continues |
| `list_directory` | `path` | One entry per line, `[FILE] name` / `[DIR] name` |
| `list_directory_with_sizes` | `path`, `sort_by?` (`"name"`/`"size"`) | `[FILE] name (123 B)` / `[DIR] name` lines; `unknown` when stat fails; totals; `size` sorts largest first |
| `directory_tree` | `path`, `exclude_patterns?`, `depth?` | Returns a JSON-serialisable list of nodes: `name`, `type`, `children` (children only for directories, omitted for files); excludes; 100k-entry bound |
| `search_files` | `path`, `pattern`, `exclude_patterns?` | Returns newline-separated paths; glob matched case-sensitively against each entry's path relative to `path`; name-based only (never file contents); excludes; 100k-entry bound; incomplete note for unreadable directories |
| `get_file_info` | `path` | Returns a mapping: size, creation/modified/access times, type, POSIX permission string, `hardLinks` |
| `list_allowed_directories` | — | Project root plus read-only roots |

### Write tools (`required_flags=("write",)`)

| Tool | Inputs | Behaviour |
|---|---|---|
| `write_file` | `path`, `content` | Overwrite in place; **fails if parent directory is missing** |
| `append_file` | `path`, `content` | Creates the file; appends exactly as given (no newline added); **fails if parent directory is missing** |
| `edit_file` | `path`, `edits[{old_text,new_text}]`, `dry_run?` | See matching rules below; all-or-nothing; `dry_run` returns a unified diff |
| `create_directory` | `path` | Creates parents; idempotent |
| `move_file` | `source`, `destination` | **Fails if destination exists**; regular-file cross-filesystem move copies then removes; cross-filesystem directory move is rejected |
| `copy_file` | `source`, `destination` | Regular files only; **fails if destination exists** |
| `delete_path` | `path`, `recursive?` (default false) | Files always; directories only when empty unless `recursive=true`; never an allowed root; symlinks are unlinked, never followed |

## `edit_file` matching rules

1. Normalize CRLF/CR to LF for matching, remember the file's dominant style.
2. Try an exact substring match first.
3. Otherwise match whole lines where each line is equal after stripping
   leading/trailing whitespace (whitespace *inside* a line must still match).
4. Replacement lines take the indentation of the line they replace.
5. Apply edits in order with correct positioning; if any edit has no match,
   apply nothing and raise an error naming the edit.
6. Preserve the file's original line endings on write.
7. `dry_run` returns a unified diff; otherwise returns a confirmation.

## Image pipeline (`read_media_file`)

- Open with Pillow. Downscale so the longest edge is at most
  `media_max_dimension` (default **1568**), preserving aspect ratio.
- Preserve transparency (RGBA when present, otherwise RGB).
- Encode PNG with optimization. If the result exceeds `media_max_bytes`
  (default **1_500_000**), progressively reduce dimensions until it fits.
- Return `ToolReturn(f"<path>: <w>x<h>, <bytes> bytes, image/png",
  content=[BinaryContent(data=png, media_type="image/png")])`.
- Non-image media: detect MIME, return `BinaryContent` with that MIME type.
- Missing Pillow support for a format falls back to the other-binary path.

## Bounds and timeouts

- Path resolution, file reads, and each directory read: at most **15 s**
  (`asyncio.wait_for(asyncio.to_thread(...))`).
- `search_files` and `directory_tree`: at most **100,000** visited entries;
  exceeding the cap is an error, not a partial result.
- Excludes are skipped before resolution/reading.
- A timed-out blocking call cannot be cancelled (it finishes in the
  background); documented limitation.

## Path containment

- `_resolve(path, write)`: resolve symlinks (`Path.resolve()`), then require the
  result to equal or be inside the project root (writes) or the project root /
  read-only roots (reads). Escapes raise `PathEscapesRootError`.
- `delete_path` resolves the **parent**, verifies containment, then removes the
  final component without following it (symlink = unlink).
- Documented limitation: check-then-use race on Windows (no per-directory
  handle / openat equivalent in Python's stdlib).

## Hook mechanism

```python
@dataclass
class ToolHookContext:
    tool_name: str
    args: dict
    root: pathlib.Path
    result: object

ToolHook = Callable[[ToolHookContext], Awaitable[str | None]]
```

- `ToolRegistry(hooks=[...])` wraps each native tool at registration: execute
  the tool, then each hook; append non-empty string returns to a **string**
  result, separated by `\n\n` (a single `\n\n` between the original result and
  the first hook output).
- Hook exceptions are logged and swallowed; they never fail the tool call.
- Non-string results (e.g. the `ToolReturn` from `read_media_file`) still run
  hooks but cannot receive appended text.
- `build_registry(..., hooks=...)` plumbs the list, so a future LSP hook can
  filter on `ctx.tool_name in {"write_file", "edit_file"}` without touching
  tool code.

## Wiring and UI

- `runtime.build_registry` registers all tools above with their flags.
- `AgentsPage.NATIVE_TOOLS` lists the full set as checkboxes, unchecked by
  default; `tool_bindings` still selects the subset.
- Modes continue to gate on the `write` flag.

## Settings

- `media_max_dimension: int = 1568`
- `media_max_bytes: int = 1_500_000`

Passed through `build_registry` to the toolbox (defaults keep tests simple).

## Testing

- Per-tool unit tests covering parity edge cases: `head`/`tail`, listing
  formats, sizes/sorting, JSON tree with depth and excludes, glob search with
  excludes, `hardLinks`, fuzzy edit with CRLF and dry-run diff, fails-if-parent
  on write/append, fails-if-destination-exists on move/copy, guarded delete.
- Image tests: PNG output, longest-edge downscale, byte cap, MIME for audio.
- Hook tests: append to string result, non-string skipped, exception isolation.
- Runtime test: every tool registered with the expected flag.
- Update `test_filesystem_tools.py` and `test_tool_registry.py`.

## Out of scope

- MCP `file://` resource template (native tools only).
- Windows ADS / reserved device name / trailing dot-space guards.
- OS-level race hardening.
- Language server integration itself (hooks only provide the seam).
