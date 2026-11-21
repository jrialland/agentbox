# UX-3 - Contextual Help and Structured Editors

- **Date:** 2026-11-21
- **Status:** Draft (design approved; pending spec review)
- **Sub-project:** UX-3 - in-app help, provider setup and connection testing, the A2A card editor, agent tool/mode/MCP guidance, API scope explanations, guided empty states, and first-run onboarding.
- **Source:** [`docs/reviews/2026-11-20-ux-review/report.md`](../../reviews/2026-11-20-ux-review/report.md) findings F1-F4, D2, D5, D7, C3-C4.
- **Roadmap:** `UX-3` in [`docs/ROADMAP.md`](../../ROADMAP.md).

## 1. Context and scope

The product can be configured end-to-end, but the UI assumes the user already understands providers, models, modes, tools, MCP, API scopes, and the A2A card schema. The review found unlabeled inputs, no in-app help, no provider connection test, a raw JSON card editor, inconsistent empty states, and a blank Home page.

UX-3 makes setup learnable in place and removes the remaining JSON-first configuration paths.

### 1.1 In scope

- Shared in-app help: tooltip guidance, "Learn more" links, and a help drawer.
- Provider presets, inline setup guidance, and a real connection-test endpoint.
- Structured A2A card editor with a JSON fallback.
- Grouped/searchable agent tools with descriptions and risk labels.
- Explicit mode cards and validation.
- MCP server guidance and URL validation.
- API scope descriptions, recommended defaults, empty-scope warning, and copy feedback.
- Purpose-built empty states for Providers, Agents, API Keys, and Skills.
- A first-run onboarding wizard and a data-derived setup checklist on Home.
- Storybook coverage and a UX-3 screenshot pack.

### 1.2 Out of scope

- Required-field/path validation outside the editors above, destructive confirmations, global API error propagation, 404/session-not-found states, and active navigation (UX-4).
- New agent, model, provider, A2A, MCP, or RBAC capabilities.
- An external documentation site.
- Backend persistence for onboarding progress.
- Tool or MCP server execution tests.

### 1.3 Dependencies

- UX-1 design system and shell.
- Existing provider/model/agent/session APIs and query hooks.
- Existing `list_models` provider logic.
- Existing A2A card storage contract.

## 2. Goals and success criteria

- A new user can reach a first chat session without guessing provider URLs or agent concepts.
- Provider configuration errors are caught before saving, with an actionable next step.
- Users can author a useful A2A card without hand-writing JSON; experts retain raw JSON access.
- Tool, mode, MCP, and scope meaning is available where the user makes the decision.
- Empty pages explain the next action and link into the flow.
- Existing provider, agent, chat, A2A, MCP, and RBAC behavior is preserved.

## 3. Decisions and rationale

| # | Decision | Rationale |
|---|---|---|
| D1 | **Shared typed help registry + `HelpTip` + `HelpDrawer`.** | One source of copy prevents drift between tooltips, drawers, and empty states. |
| D2 | **In-app help content, no external docs site.** | The product has no documentation domain yet; in-app content is immediately useful. |
| D3 | **Provider presets auto-fill only untouched fields.** | Speeds setup without overwriting deliberate custom URLs. |
| D4 | **Connection test uses form values through a backend endpoint.** | Validates unsaved configuration and can reuse a stored key without persisting data. |
| D5 | **Core A2A fields + skills repeater + JSON fallback.** | Covers normal use while preserving expert escape hatch. |
| D6 | **Unknown A2A fields are preserved.** | Structured edits must not silently discard valid custom card data. |
| D7 | **Full first-run wizard + Home checklist.** | Chosen scope; checklist keeps setup discoverable after dismissal. |
| D8 | **Setup progress derives from real data.** | A local flag should not claim setup is complete when resources are missing. |
| D9 | **Field errors are inline and preserve input.** | Errors should teach the next action, not erase work. |

## 4. Experience architecture

### 4.1 Help system

- `help/content.ts` exports a typed registry of help entries:
  - `id`
  - `title`
  - `summary` (tooltip-sized)
  - `sections`: heading, paragraph, bullets, optional code/example
  - optional `related` help IDs
- `HelpTip({ id })` renders a small help icon with a tooltip containing the summary and a "Learn more" action.
- `HelpLink({ id, children })` opens the same entry in the drawer.
- `HelpProvider` owns the drawer state and is mounted once in the app shell.
- The drawer renders entries with headings, lists, code examples, and related links.
- Initial help groups:
  - Provider kinds, URLs, API keys, context window.
  - Agent modes, tool categories, MCP servers, sub-agents, model labels.
  - A2A cards, capabilities, skills, and documentation URLs.
  - API scopes, empty scope meaning, and key handling.
  - Onboarding steps.

### 4.2 Provider setup

- Extract `ProviderForm` from the Providers page drawer and reuse it in onboarding.
- The kind selector uses friendly labels while storing the existing kind values.
- A typed preset map provides example base URLs and, where supported, model-list URLs.
- Presets fill a field only when it is empty or still equals the previous preset default; custom values are never overwritten.
- A compact guidance panel under the kind selector explains:
  - which URL style the kind expects
  - whether `/v1` is usually required
  - where the API key comes from
  - how model discovery works
- `Test connection` sends the current form values to the backend and renders:
  - testing state
  - success with model count, sample models, and latency
  - failure with a normalized error and next action
- Save remains independent of the test; the test never creates or updates records.

### 4.3 A2A card editor

- `AgentCardModal` gets two tabs: `Structured` and `JSON`.
- Structured fields:
  - name (required)
  - description
  - version (required)
  - provider organization and URL
  - documentation URL
  - capabilities: streaming, push notifications, state transition history
  - default input/output modes
  - skills repeater
- Each skill row edits: id, name, description, tags, and examples.
- Skills can be added, removed, and reordered.
- The original card object is retained as `rawCard`; structured edits merge known fields into it so unknown fields survive.
- The JSON tab parses into `rawCard` on success. Malformed JSON blocks saving and shows the parser message inline.
- Switching from JSON to structured is allowed only after a successful parse.
- Validation:
  - name and version required
  - documentation/provider URLs must be valid http/https URLs
  - skill IDs unique within the card
  - skill name required when a skill exists
- Save works from either tab and preserves the existing `PUT /agents/{name}/card` contract.

### 4.4 Agent configuration

- Native tools are grouped by purpose:
  - Filesystem read
  - Filesystem write
  - Web
  - Terminal
- Each tool shows a short description and a read/write risk label.
- Add search, select-all/clear, and a "show advanced" toggle for less-common tools.
- Modes become explicit cards:
  - name input
  - write-enabled toggle
  - explanation of how the mode affects tool permissions
  - add/remove controls
- Mode validation rejects blank and duplicate names.
- MCP servers become repeatable rows with:
  - URL input and http/https validation
  - remove control
  - help explaining transport, auth, and failure behavior
- Sub-agents include help for delegation behavior, latency, and cost.

### 4.5 API scopes

- Permission strings are grouped and shown with human descriptions from a frontend scope registry; unknown scopes fall back to the raw name.
- API key creation offers a recommended default selection.
- Creating a key with no scopes shows an inline warning explaining that the key will be unusable.
- The created-key modal auto-selects the secret and uses the existing copy component with visible confirmation.

### 4.6 Empty states and onboarding

- Providers, Agents, API Keys, and Skills get purpose-built empty states with:
  - what is missing
  - why it matters
  - one primary CTA
  - a help link
- Home becomes a setup hub with:
  - welcome/status header
  - setup checklist derived from real data
  - primary actions
  - recent sessions when available
- Checklist items:
  1. Provider connected
  2. Model available
  3. Agent ready
  4. First session started
- The first-run wizard auto-opens when the user has no providers and no agents and has not dismissed it.
- Wizard steps:
  1. Welcome
  2. Connect provider (shared provider form + optional test)
  3. Create agent (essentials: name, description, instructions, model, default read-only tools)
  4. Create project and first session
  5. Done
- Each step is skippable and keeps inputs on failure.
- Dismissal is stored in `localStorage` under `agentbox-onboarding-v1`.
- Real resources remain the source of truth for completion; the Home checklist reopens the wizard at the first incomplete step.

## 5. Backend design

### 5.1 Provider test endpoint

`POST /providers/test` requires `providers:create`.

Request:

```json
{
  "kind": "deepseek",
  "base_url": "https://api.deepseek.com/v1",
  "models_url": "https://api.deepseek.com/v1/models",
  "api_key": "optional",
  "provider_id": "optional-existing-provider"
}
```

Behavior:

- Validate `kind` and URL schemes (`http`/`https`).
- If `provider_id` is supplied and `api_key` is blank, load the stored key.
- Resolve a transient `Provider`; do not insert or update rows.
- Reuse the existing provider model-list fetch.
- Timeout after 10 seconds.
- Never log or return the API key.

Response:

```json
{
  "ok": true,
  "latency_ms": 420,
  "model_count": 12,
  "sample_models": ["model-a", "model-b"],
  "error": null
}
```

Failure responses still return HTTP 200 with `ok: false` and a normalized error:

```json
{
  "ok": false,
  "latency_ms": 10000,
  "model_count": null,
  "sample_models": [],
  "error": {
    "code": "timeout",
    "message": "The provider did not answer within 10 seconds. Check the URL and network."
  }
}
```

Error codes: `invalid_url`, `unauthorized`, `not_found`, `timeout`, `connection_failed`, `no_models_url`, `unknown`.

### 5.2 Persistence and contracts

- No database migration.
- No change to provider, agent, A2A card, API key, or session persistence.
- A2A validation is frontend-only.
- `openapi.json` and `apps/web/src/api/schema.d.ts` are regenerated for the test endpoint.

## 6. Error handling

- Provider test failures use the normalized code to show an action:
  - `unauthorized`: check the API key
  - `not_found`: check the models URL
  - `invalid_url`: use an http/https URL
  - `timeout` / `connection_failed`: check network or provider availability
  - `no_models_url`: enter a model-list endpoint
- Provider save failures remain visible and preserve form input.
- A2A and agent validation errors render next to the field.
- Onboarding failures stay on the current step and keep inputs.
- Help content avoids raw stack traces and backend exception text.

## 7. Components

- `src/help/HelpProvider.tsx`, `HelpDrawer.tsx`, `HelpTip.tsx`, `HelpLink.tsx`, `content.ts`.
- `src/pages/providers/ProviderForm.tsx`, `providerPresets.ts`, `ProviderTestResult.tsx`.
- `src/pages/agents/AgentCardModal.tsx` (structured + JSON modes).
- `src/pages/agents/AgentToolsEditor.tsx`, `AgentModesEditor.tsx`, `AgentMcpEditor.tsx`.
- `src/pages/api-keys/scopeHelp.ts`.
- `src/onboarding/OnboardingWizard.tsx`, `HomeChecklist.tsx`, `onboardingProgress.ts`.
- Empty-state usage through the existing `EmptyState` pattern.

## 8. Testing

### 8.1 Backend

- Provider test success with a stub model server.
- Unauthorized response normalization.
- Missing models URL.
- Timeout or connection failure normalization.
- Stored-key reuse for an existing provider with a blank key.
- Test does not create or modify provider/model rows.

### 8.2 Frontend unit

- Help registry lookup and drawer rendering.
- `HelpTip` and `HelpLink` open the correct entry.
- Provider presets fill untouched fields and preserve custom values.
- Provider test success/failure states.
- A2A structured-to-card serialization.
- Unknown A2A fields preserved.
- Malformed JSON blocks save.
- Skill ID uniqueness and URL validation.
- Mode blank/duplicate validation.
- Scope grouping and empty-scope warning.
- Onboarding progress derivation and first-incomplete-step selection.

### 8.3 E2E

- First-run wizard: provider test fails, fix, test succeeds, create provider, create agent, create session.
- Provider preset auto-fill, connection test, and save.
- A2A structured save and JSON round-trip.
- Invalid A2A JSON blocks saving with an inline error.
- Agent tools grouping/search, mode duplicate rejection, MCP URL validation.
- API key empty-scope warning and copy confirmation.
- Home checklist links to the correct setup step.
- Empty states link to their creation flows.

### 8.4 Visual

- Storybook stories for help drawer/tip, provider form states, A2A structured/JSON, grouped tools/modes, onboarding steps, and empty states.
- Screenshot pack under `docs/reviews/2026-11-21-ux-3/`.

## 9. Delivery order

1. Help primitives and registry.
2. Provider presets, shared form, and backend connection test.
3. Structured A2A editor.
4. Agent tools/modes/MCP editors and guidance.
5. API scope help and key creation feedback.
6. Home checklist and onboarding wizard.
7. Empty states, Storybook, screenshot pack, E2E, final verification.

## 10. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Wizard scope creep | Reuse page forms and mutations; keep each step to its essentials. |
| Help copy drift | Single typed registry consumed by tips, drawer, and empty states. |
| A2A unknown-field loss | Merge known fields into the preserved raw card. |
| Provider test hangs or leaks secrets | 10s timeout, http/https only, authenticated permission, no key logging, no persistence. |
| Full UX-3 is large | Deliver in the ordered layers above; each layer is independently testable. |
| Preset URLs become stale | Presets are editable examples, not validation rules; connection test is the source of truth. |
