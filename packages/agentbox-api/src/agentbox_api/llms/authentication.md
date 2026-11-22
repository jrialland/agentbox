# Authentication

The `/llms.txt` and `/llms/*.md` files, `/openapi.json`, `/docs`, and `/sandbox` are public. `POST /auth/login` and `POST /auth/register` are also public. All other API routes require a bearer credential.

## JWT login

`POST /auth/login` with JSON:

```json
{"username": "admin", "password": "admin"}
```

The response is `{"access_token": "<jwt>", "token_type": "bearer"}`. Send it on every request:

```bash
curl -sS "$AGENTBOX_URL/auth/me" \
  -H "Authorization: Bearer $TOKEN"
```

JWTs expire after the configured lifetime (default one hour). Log in again when the API returns `401`.

## API keys

Personal API keys are long-lived bearer credentials. Create one with an authenticated JWT:

```bash
curl -sS -X POST "$AGENTBOX_URL/api-keys" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"scopes": ["sessions:read", "sessions:create"], "expires_at": "2026-12-31T00:00:00Z"}'
```

The raw `key` is returned once; store it. Use it exactly like a JWT:

```bash
curl -sS "$AGENTBOX_URL/sessions" \
  -H "Authorization: Bearer $TOKEN"
```

`scopes` must be a subset of the scopes held by the user creating the key. `expires_at` is optional but must be in the future. Revoke a key with `DELETE /api-keys/{id}`.

## Scopes and errors

A credential carries permission scopes such as `sessions:create`, `agents:read`, or `providers:create`. Each route checks its own scope.

- `401 Unauthorized`: missing, expired, revoked, or invalid credential.
- `403 Forbidden`: valid credential without the required scope.
- `GET /auth/me` returns the current user id, username, and scopes.
