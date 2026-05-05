# Production Evidence Gate

This is the remaining P6 gate before deleting SQLite compatibility code.

The project must not remove SQLite write paths, `_repo_backend` branches, or
`legacy_payload_json` compatibility queries until the target production
environment has a validated evidence bundle.

## Evidence File

Use the template:

```powershell
.\venv\Scripts\python.exe scripts\production_evidence.py --write-template docs\product\PRODUCTION_EVIDENCE.prod.json
```

Fill `PRODUCTION_EVIDENCE.prod.json` from production outputs:

- MySQL backup artifact name, size, sha256, and restore-check target.
- Schema validation, reconciliation, idempotent rerun, and rollback drill result.
- Soak window with at least two `/api/v1/readiness` samples.
- Readiness samples must show MySQL, Redis cache, Redis task queue, standalone worker execution, all repository backends as MySQL, and zero stale tasks.

Validate:

```powershell
.\venv\Scripts\python.exe scripts\production_evidence.py --evidence docs\product\PRODUCTION_EVIDENCE.prod.json
```

## SQLite Retirement Rule

Only when `production evidence passed` is returned:

1. Delete SQLite write path.
2. Re-run the full verification suite.
3. Delete `_repo_backend` and dual-backend legacy branches.
4. Re-run production evidence validation.
5. Delete `legacy_payload_json` compatibility queries after confirming no rollback reads need them.

If any evidence check fails, keep production fail-closed guards and SQLite
compatibility branches in place.
