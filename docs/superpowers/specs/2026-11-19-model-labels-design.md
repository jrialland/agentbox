# Model Labels and Label-Based Routing — Design

Date: 2026-11-19
Status: Approved (design), spec awaiting review.

## Goal

Let users tag models with labels (`cheap`, `fast`, `highend`, …), manage those
labels implicitly while editing a model, and bind an agent either to a concrete
model or to a label. A label-bound agent resolves to a concrete model at load
time using a deterministic per-link priority, so routing changes take effect
without editing the agent. The resolver is a reusable service for future
sub-agent strength selection (D8).

## Decisions

- **Normalized** storage: `Label` + `ModelLabelLink` tables (not a JSON column).
- **Full routing** now, with per-link `priority` (lowest wins; ties by provider
  name, then model name).
- **Unified model/label selector** in the agent form; existing agents keep
  working.
- **Implicit label creation**: typing a new name while assigning creates it.
  No standalone rename/delete UI; labels with no links remain as suggestions.
- **Snapshot + dynamic re-resolve**: an agent keeps a non-null `model_id`
  snapshot and gains `model_label`; the repository re-resolves the label on
  every load. No nullable `model_id` migration.

## Data model

`agentbox_models/tables/core.py`:

```python
class Label(SQLModel, table=True):
    id: str = Field(primary_key=True)
    name: str = Field(index=True, unique=True)  # canonical lowercase


class ModelLabelLink(SQLModel, table=True):
    model_id: str = Field(foreign_key="model.id", primary_key=True)
    label_id: str = Field(foreign_key="label.id", primary_key=True)
    priority: int = 0  # lower wins
```

`Agent` gains `model_label: str | None = None` (canonical lowercase). `model_id`
stays non-null.

Alembic revision `model_labels` (down_revision `7a1c2f3d4e5b`) creates both
tables with their indexes.

### Canonical label names

`canonical_label(name) = " ".join(name.strip().lower().split())`.
Reject empty results and names longer than 40 characters. Uniqueness is on the
canonical name, so `Fast`, `fast`, and ` fast ` are the same label.

## Resolution

New module `agentbox_models/repos/model_labels.py`:

```python
async def resolve_model_label(factory, label: str, provider: str | None = None):
    # join Model -> ModelLabelLink -> Label -> Provider
    # where lower(Label.name) == canonical_label(label)
    # optional Provider.name == provider
    # order by ModelLabelLink.priority ASC, Provider.name ASC, Model.name ASC
```

Returns the first `Model` or `None`. Used by `AgentRepository` and available to
future sub-agent tools.

`AgentRepository.save()`:

- If `spec.model_label` is set, resolve it; if no model matches, raise
  `ValueError("No model for label: <label>")`. Store the resolved `model_id`
  snapshot and the canonical `model_label`.
- Otherwise behave as today (resolve by model name).

`AgentRepository.load()`:

- If `row.model_label` is set, resolve it now; build `ModelBinding` from the
  resolved model/provider. If resolution fails (all models for the label were
  deleted), fall back to the stored `row.model_id` snapshot.
- Otherwise load by `row.model_id` as today.

`AgentSpec` (harness) gains `model_label: str | None = None`; `model_binding`
still holds the resolved concrete model. Harness execution is unchanged.

## API

All existing model endpoints switch to a `ModelRead` schema that includes
labels.

- `GET /labels` → `LabelRead[] { id, name }` — permission `providers:read`.
  Suggestions only; ordering by name.
- `GET /models` and `POST /providers/{pid}/models/refresh` →
  `ModelRead[] { id, provider_id, name, labels: [{ id, name, priority }] }`
  (labels ordered by name).
- `POST /models` body gains optional `labels: [{ label: str, priority: int = 0 }]`;
  returns `ModelRead`.
- `PUT /models/{mid}/labels` body `{ labels: [{ label: str, priority: int = 0 }] }`
  replaces the model's label set (implicit upsert by canonical name; duplicate
  canonical names keep the last priority). Returns `ModelRead`. Permission
  `providers:create`.
- `DELETE /models/{mid}` and provider cascade deletion also delete the model's
  `ModelLabelLink` rows.
- `AgentCreate`: `model: str | None = None`, `model_label: str | None = None`;
  exactly one must be set (400 otherwise). `AgentSpec` responses include
  `model_label` (resolved `model` remains the concrete model name).

## UI

### Models tab (`ProvidersPage`)

- A “Labels” column renders each model's labels as `Badge`s (with priority in a
  tooltip).
- A label filter above the table (client-side) narrows the visible models.
- An “Edit labels” action per row opens a modal listing `[label name]
  [priority]` rows with add/remove. Suggestions come from `GET /labels`; a new
  typed name is created implicitly. Saving calls
  `PUT /models/{mid}/labels`.

### Agents form (`AgentsPage`)

- The Model selector lists concrete models as `"<provider> · <model>"` and
  labels as `"label: <name>"`.
- Selecting a concrete model sends `model`; selecting a label sends
  `model_label` (and omits `model`).
- The agents table shows the resolved model and a label badge when the agent is
  label-bound.

## Tests

API (`test_model_labels.py`):

- implicit label creation, case-folding/whitespace, dedupe;
- replace-set assignment and priority updates;
- `GET /models` includes labels; `GET /labels` suggestions;
- priority resolution: lower priority wins; ties break by provider then model;
- label-bound agent: save stores snapshot + label, load resolves the label,
  priority change is reflected on the next load;
- deleting a model and deleting a provider remove link rows;
- `AgentCreate` rejects neither/both of `model` and `model_label`.

E2E (`provider-model-admin.spec.ts`):

- assign labels to a model, see badges, filter by label;
- create an agent bound to a label and verify the resolved model + badge.

Models package: a label/link roundtrip test.

## Out of scope

- Standalone label rename/delete UI (implicit creation only; orphan labels
  remain suggestions).
- Server-side label filtering (client-side in the Models tab).
- Labels on providers or sessions.
- Sub-agent tools that consume labels (D8); the resolver is the seam for them.
- Changing the existing model-name binding semantics for non-label agents.
