# API Reference

Every route is relative to this origin. The permission column is the scope required by `require_permission`; `public` means no credential and `authenticated` means any valid credential. Exact schemas are in [openapi.json](/openapi.json).

## Auth

| Method | Path | Permission | Purpose |
|---|---|---|---|
| POST | `/auth/login` | public | Exchange username/password for a JWT |
| POST | `/auth/register` | public | Register a user |
| GET | `/auth/me` | authenticated | Current user id, username, and scopes |

## Agents

| Method | Path | Permission | Purpose |
|---|---|---|---|
| POST | `/agents` | `agents:create` | Create an agent configuration |
| GET | `/agents` | `agents:read` | List agent configurations |
| GET | `/agents/{name}` | `agents:read` | Read one configuration |
| PUT | `/agents/{name}` | `agents:create` | Replace a configuration |
| DELETE | `/agents/{name}` | `agents:delete` | Delete a configuration |
| GET | `/agents/{name}/avatar` | `agents:read` | Read the avatar |
| PUT | `/agents/{name}/avatar` | `agents:create` | Upload an avatar |
| DELETE | `/agents/{name}/avatar` | `agents:create` | Reset the avatar |
| GET | `/agents/{name}/card` | `agents:read` | Read the A2A card |
| PUT | `/agents/{name}/card` | `agents:create` | Store the A2A card |
| DELETE | `/agents/{name}/card` | `agents:create` | Remove the A2A card |

## Projects and sessions

| Method | Path | Permission | Purpose |
|---|---|---|---|
| POST | `/projects` | `projects:create` | Create a project |
| GET | `/projects` | `projects:read` | List projects |
| GET | `/projects/{pid}` | `projects:read` | Read a project |
| PUT | `/projects/{pid}` | `projects:create` | Rename a project or set extra roots |
| DELETE | `/projects/{pid}` | `projects:delete` | Delete a project |
| POST | `/sessions` | `sessions:create` | Create a session |
| GET | `/sessions` | `sessions:read` | List root sessions |
| GET | `/sessions/{sid}` | `sessions:read` | Read a session |
| PATCH | `/sessions/{sid}` | `sessions:create` | Rename a session |
| DELETE | `/sessions/{sid}` | `sessions:create` | Delete a session |
| GET | `/sessions/{sid}/messages` | `sessions:read` | Read active history |
| POST | `/sessions/{sid}/messages` | `sessions:create` | Send a message and stream the run |
| POST | `/sessions/{sid}/messages/cancel` | `sessions:create` | Cancel the active run |
| POST | `/sessions/{sid}/attachments` | `sessions:create` | Upload an attachment |
| GET | `/sessions/{sid}/attachments/{aid}` | `sessions:read` | Download an attachment |
| GET | `/sessions/{sid}/files` | `sessions:read` | List project files |
| GET | `/sessions/{sid}/plan` | `sessions:read` | Read the session plan |
| GET | `/sessions/{sid}/lsp` | `sessions:read` | Read LSP state and snapshots |
| POST | `/sessions/{sid}/mcp/{server_id}/resources/read` | `sessions:create` | Relay an MCP resource read |
| POST | `/sessions/{sid}/mcp/{server_id}/tools/call` | `sessions:create` | Relay an MCP tool call |

## Providers, models, and labels

| Method | Path | Permission | Purpose |
|---|---|---|---|
| POST | `/providers` | `providers:create` | Create a provider |
| GET | `/providers` | `providers:read` | List providers |
| POST | `/providers/test` | `providers:create` | Test provider connectivity |
| PUT | `/providers/{pid}` | `providers:create` | Update a provider |
| POST | `/providers/{pid}/models/refresh` | `providers:list-models` | Refresh models from the provider |
| DELETE | `/providers/{pid}` | `providers:delete` | Delete a provider |
| GET | `/models` | `providers:read` | List models |
| POST | `/models` | `providers:create` | Create a model |
| PUT | `/models/{mid}/labels` | `providers:create` | Replace model labels |
| DELETE | `/models/{mid}` | `providers:create` | Delete a model |
| GET | `/labels` | `providers:read` | List model labels |

## Skills, prompts, and plugins

| Method | Path | Permission | Purpose |
|---|---|---|---|
| GET | `/skills` | `agents:read` | List skills |
| GET | `/skills/{name}` | `agents:read` | Read a skill |
| PUT | `/skills/{name}` | `agents:create` | Create or update a skill |
| DELETE | `/skills/{name}` | `agents:create` | Delete a skill |
| POST | `/prompts/preview` | `agents:create` | Preview prompt templating |
| GET | `/plugins` | `plugins:read` | List plugins |
| GET | `/plugins/{scope}/{name}` | `plugins:read` | Read a plugin |
| PUT | `/plugins/state` | `plugins:write` | Enable or disable a plugin |

## Administration

| Method | Path | Permission | Purpose |
|---|---|---|---|
| POST | `/users` | `users:manage` | Create a user |
| GET | `/users` | `users:manage` | List users |
| PUT | `/users/{uid}` | `users:manage` | Update a user |
| GET | `/users/{uid}/roles` | `users:manage` | List user roles |
| PUT | `/users/{uid}/roles` | `users:manage` | Replace user roles |
| DELETE | `/users/{uid}` | `users:manage` | Delete a user |
| POST | `/roles` | `roles:manage` | Create a role |
| GET | `/roles` | `roles:manage` | List roles |
| PUT | `/roles/{rid}` | `roles:manage` | Update a role |
| GET | `/roles/{rid}/permissions` | `roles:manage` | List role permissions |
| PUT | `/roles/{rid}/permissions` | `roles:manage` | Replace role permissions |
| DELETE | `/roles/{rid}` | `roles:manage` | Delete a role |
| GET | `/permissions` | `roles:manage` | List permissions |
| POST | `/permissions` | `roles:manage` | Create a permission |
| PUT | `/permissions/{pid}` | `roles:manage` | Update a permission |
| DELETE | `/permissions/{pid}` | `roles:manage` | Delete a permission |
| POST | `/api-keys` | `api_keys:manage` | Create an API key |
| GET | `/api-keys` | `api_keys:manage` | List API keys |
| DELETE | `/api-keys/{kid}` | `api_keys:manage` | Revoke an API key |

## Protocols and documentation

| Method | Path | Permission | Purpose |
|---|---|---|---|
| GET | `/a2a/{agent}/.well-known/agent-card.json` | bearer + `sessions:create` | Read an agent card |
| POST | `/a2a/{agent}` | bearer + `sessions:create` | A2A JSON-RPC |
| GET | `/sandbox` | public | MCP App sandbox page |
| GET | `/llms.txt` | public | This guide's index |
| GET | `/llms/{filename}` | public | A guide section |
| GET | `/openapi.json` | public | Machine-readable schema |
| GET | `/docs` | public | Interactive API docs |

## Errors

Errors use `{"detail": "..."}` (A2A uses `{"error": "..."}`).

- `400`: invalid request or unknown referenced object in a body.
- `401`: missing or invalid credential.
- `403`: valid credential without the required scope.
- `404`: unknown session, agent, project, or guide file.
- `409`: cancel requested with no active run.
- `422`: request validation failure.

Retry idempotent reads after transient network failures. Do not retry a message send automatically; check the session history first.
