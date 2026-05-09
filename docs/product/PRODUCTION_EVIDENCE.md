# Production Evidence Gate

This is the v1.0 P0 launch evidence gate and the later P6 gate before deleting SQLite compatibility code.

The v1.0 launch gate requires backup/restore, migration, release, security,
regression, and soak evidence. SQLite retirement checks are still reported, but
are advisory for v1.0 and are not required for `core_evidence_ok`.

The project must not remove SQLite write paths, `_repo_backend` branches, or
`legacy_payload_json` compatibility queries until the target production
environment has a validated evidence bundle and the SQLite retirement advisory
checks have been explicitly approved.

## Evidence File

Use the template:

```powershell
.\venv\Scripts\python.exe scripts\production_evidence.py --write-template docs\product\PRODUCTION_EVIDENCE.prod.json
```

Fill `PRODUCTION_EVIDENCE.prod.json` from production outputs:

- MySQL backup artifact name, size, sha256, and restore-check target.
- Schema validation, reconciliation, idempotent rerun, rollback drill result, and Alembic revision `0022_stock_daily_bar_timestamps`.
- Release evidence: deploy preflight, repository hygiene, rollback plan review, and release notes review.
- Security evidence: rotated secrets/admin password, reviewed public ports, verified CSRF/security headers, and `LIVE_BROKER_LAUNCH_POLICY=disabled` for v1.0.
- Regression evidence: backend tests, frontend build, smoke tests, test time, and commands.
- Soak window with at least two `/api/v1/readiness` samples.
- Readiness samples must show MySQL, Redis cache, Redis task queue, standalone worker execution, all repository backends as MySQL including `TRADING_REPOSITORY_BACKEND`, and zero stale tasks.

Validate:

```powershell
.\venv\Scripts\python.exe scripts\production_evidence.py --evidence docs\product\PRODUCTION_EVIDENCE.prod.json
```

## Launch Rule

`production evidence passed` means the v1.0 core evidence is complete. Missing
backup/restore/soak/security/regression/release evidence fails the launch gate.
Missing SQLite retirement approvals only keeps `sqlite_retirement_ok=false`.

## SQLite Retirement Rule

Only when `production evidence passed` and all SQLite retirement advisory checks are approved:

1. Delete SQLite write path.
2. Re-run the full verification suite.
3. Delete `_repo_backend` and dual-backend legacy branches.
4. Re-run production evidence validation.
5. Delete `legacy_payload_json` compatibility queries after confirming no rollback reads need them.

If any evidence check fails, keep production fail-closed guards and SQLite
compatibility branches in place.
