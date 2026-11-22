# Agentbox Security Report

Generates a light, print-first HTML security audit report with severity charts, a machine-readable
JSON snapshot, and an A4 PDF.

## Usage

From the repository root:

```powershell
just security-report
just security-report --no-pdf
just security-report --fail-on high
just security-report ../another-project --out reports/security/other
```

Artifacts are written to `reports/security/` (gitignored):

- `agentbox-security-<shortsha>-<timestamp>.html`
- `agentbox-security-<shortsha>-<timestamp>.pdf`
- `agentbox-security-<shortsha>-<timestamp>.json`
- `latest.html`, `latest.pdf`, `latest.json`

## Scanners

| Section | Ecosystem | Tool | Structured input |
| --- | --- | --- | --- |
| SCA | Python | PySentry | `--format json` |
| SCA | JavaScript | Bun audit / NPM audit | `--json` |
| SAST | Python | Bandit | `-f json` |
| SAST | JavaScript/TypeScript | JS-X-Ray | in-process warning objects |

Tests, fixtures, specs, and stories are excluded from SAST by default; pass `--include-tests` to
include them. Dependency and generated directories (`.venv`, `node_modules`, `dist`, `build`,
`coverage`, caches) are always excluded.

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | A scanner is partial/failed, or PDF generation failed |
| 2 | Usage/configuration error |
| 3 | `--fail-on` threshold met |

Findings do not fail the run unless `--fail-on` is set.

## Development

```powershell
bun install --cwd scripts/security-report
bun run --cwd scripts/security-report test
bun run --cwd scripts/security-report typecheck
$env:SECURITY_REPORT_PDF_TEST="1"; bun run --cwd scripts/security-report test -- src/pdf.test.ts
```
