# P6 Staging Migration Report - 2026-05-04

## Environment

- Runtime: Docker Compose local staging
- Services: `mysql`, `redis`, one-shot `backend`
- MySQL schema revision: `0003_picks_legacy_payload_json`
- Migration pipeline: `scripts/staging_mysql_migration.py`
- Source SQLite in container: `/app/data/picks.db`
- Source SQLite sha256: `058570575d95fd6a79b83a8832b82c77b0fb200bf97f3744c7f0bea147dcae57`

## Default Pipeline

Command:

```powershell
docker compose run --rm -e MARKET_DATA_PROVIDER=mootdx -e MARKET_DATA_FALLBACKS=akshare -e ALLOW_MOCK_MARKET_DATA=0 backend python scripts/staging_mysql_migration.py
```

Result:
- Alembic upgrade: passed
- Bootstrap seed: passed
- Schema validation: passed
- Resolve dry-run: passed
- `unresolved_strategy_rows`: 0
- `planned_rows`: 6
- `duplicate_rows`: 0
- `skipped_invalid`: 0
- `issues`: 0
- `target_preconditions.ok`: true
- Warnings: 0

## Apply Pipeline

Command:

```powershell
docker compose run --rm -e MARKET_DATA_PROVIDER=mootdx -e MARKET_DATA_FALLBACKS=akshare -e ALLOW_MOCK_MARKET_DATA=0 backend python scripts/staging_mysql_migration.py --apply --confirm-apply sqlite-to-mysql-picks
```

First apply result:
- `inserted`: 6
- `existing`: 0
- `duplicates`: 0
- reconciliation: passed
- `matched_rows`: 6
- `missing_rows`: 0
- `mismatch_rows`: 0

Idempotent re-run result:
- `inserted`: 0
- `existing`: 6
- `backfilled_existing`: 0 after `0003`; legacy payload backfill had already completed
- `duplicates`: 0
- reconciliation: passed
- `matched_rows`: 6
- `missing_rows`: 0
- `mismatch_rows`: 0

## Database Spot Check

Read-only SQLAlchemy check from backend container:
- `SELECT COUNT(*) FROM picks`: 6
- Grouped result: `(tenant_id=1, source='auto_scan', count=6)`
- `SELECT COUNT(*) FROM picks WHERE legacy_payload_json IS NOT NULL`: 6

## Backup And Restore Drill

SQLite isolated backup/restore drill:
- Command: `.\venv\Scripts\python.exe scripts\backup_restore_drill.py --json`
- Result: passed
- Restored drill rows: 1

MySQL staging dump/restore check:
- Dump command used `mysqldump --single-transaction --no-tablespaces`.
- Restore target: isolated `restore_check` database.
- Restored `picks` count: 6
- Restored `legacy_payload_json IS NOT NULL` count: 6

## Legacy Payload

The migration now preserves legacy-only context in `picks.legacy_payload_json`:
- `pick_price`
- `ma25`
- `vol_ratio`
- `last_price`
- `quote_time`
- `content_title`
- `content_ref`

Current status: no migration warning remains for these fields.
