# P6 Staging Migration Report - 2026-05-04

## Environment

- Runtime: Docker Compose local staging
- Services: `mysql`, `redis`, one-shot `backend`
- MySQL schema revision: `0011_user_engagement_fields`
- Migration pipeline: `scripts/staging_mysql_migration.py`
- Source SQLite in container: `/app/data/picks.db`
- Source SQLite sha256: `e39104f396860e64302827bcbba319ecd38bb63aebda38aea42bd40bacadb08e`
- Source SQLite size: `196608` bytes
- Execution time: `2026-05-04 20:39:42 +08:00`

## Direct Resolve Dry Run

Command:

```powershell
docker compose run --rm -e MARKET_DATA_PROVIDER=mootdx -e MARKET_DATA_FALLBACKS=akshare -e ALLOW_MOCK_MARKET_DATA=0 backend python scripts/migrate_sqlite_to_mysql.py --resolve-strategies --json
```

Result:

- `target_preconditions.ok`: true
- `tenant_exists`: true
- `tenant_id`: 1
- `strategy_map_size`: 14
- `total_source_rows`: 6
- `planned_rows`: 6
- `duplicate_rows`: 0
- `skipped_archived`: 0
- `skipped_invalid`: 0
- `unresolved_strategy_rows`: 0
- `issues`: 0

Legacy source counts:

- `picks`: 6
- `strategies`: 6
- `strategy_pools`: 5
- `backtest_results`: 4
- `operation_logs`: 57
- `research_reports`: 1
- `saved_filters`: 0
- `ui_settings`: 1

## Apply And Reconciliation

Command:

```powershell
docker compose run --rm -e MARKET_DATA_PROVIDER=mootdx -e MARKET_DATA_FALLBACKS=akshare -e ALLOW_MOCK_MARKET_DATA=0 backend python scripts/migrate_sqlite_to_mysql.py --apply --confirm-apply sqlite-to-mysql-picks --json
```

Result:

- `apply_gate.ok`: true
- `apply_gate.blockers`: 0
- `apply_gate.warnings`: 0
- `inserted`: 0
- `existing`: 6
- `backfilled_existing`: 0
- `duplicates`: 0
- `reconciliation.ok`: true
- `expected_rows`: 6
- `matched_rows`: 6
- `missing_rows`: 0
- `mismatch_rows`: 0
- `field_mismatches`: 0

This staging database already contained the earlier successful migration. The
current apply therefore validated repeatable writes by matching the six migrated
rows instead of inserting duplicates.

Auxiliary apply result:

- `strategies`: inserted 0, existing 6, updated 6
- `ui_settings`: inserted 0, updated 1
- `saved_filters`: inserted 0, existing 0
- `operation_logs`: inserted 0, existing 57
- `strategy_pools`: inserted 0, existing 5, updated 5
- `backtest_results`: inserted 0, existing 4
- `research_reports`: inserted 0, existing 1, updated 1

## Idempotent Re-Run

Command:

```powershell
docker compose run --rm -e MARKET_DATA_PROVIDER=mootdx -e MARKET_DATA_FALLBACKS=akshare -e ALLOW_MOCK_MARKET_DATA=0 backend python scripts/migrate_sqlite_to_mysql.py --apply --confirm-apply sqlite-to-mysql-picks --json
```

Result:

- `inserted`: 0
- `existing`: 6
- `duplicates`: 0
- `reconciliation.ok`: true
- `matched_rows`: 6
- `missing_rows`: 0
- `mismatch_rows`: 0

## Verify

Command:

```powershell
docker compose run --rm -e MARKET_DATA_PROVIDER=mootdx -e MARKET_DATA_FALLBACKS=akshare -e ALLOW_MOCK_MARKET_DATA=0 backend python scripts/migrate_sqlite_to_mysql.py --verify --json
```

Result:

- `reconciliation.ok`: true
- `expected_rows`: 6
- `matched_rows`: 6
- `missing_rows`: 0
- `mismatch_rows`: 0
- `field_mismatches`: 0

## Database Spot Check

Read-only SQL checks from the staging MySQL container:

- Unique key exists: `uk_picks_tenant_date_symbol_source` on `tenant_id + trade_date + symbol + source`.
- MySQL `picks` total rows: 7.
- Migrated slice: `(tenant_id=1, source='auto_scan', count=6)`.
- Existing non-migration staging smoke row: `(tenant_id=1, source='csv-import', count=1)`.
- Non-default tenant rows in `picks`: 0.
- Rows with null `strategy_id`: 0.
- Rows with orphan `strategy_id`: 0.
- Duplicate key groups for `tenant_id + trade_date + symbol + source`: 0.
- Migrated rows map to strategy `2560` / `2560战法`.
- Rows with `legacy_payload_json IS NOT NULL`: 7.

The migration reconciliation is scoped to the six planned legacy SQLite rows.
The extra `csv-import` row is pre-existing staging smoke data and was not
created by the migration run.

## Full Staging Pipeline

Command:

```powershell
docker compose run --rm -e MARKET_DATA_PROVIDER=mootdx -e MARKET_DATA_FALLBACKS=akshare -e ALLOW_MOCK_MARKET_DATA=0 backend python scripts/staging_mysql_migration.py --apply --confirm-apply sqlite-to-mysql-picks
```

Result:

- Pipeline: passed
- Alembic upgrade: passed
- Bootstrap seed: passed
- Schema validation: passed at `0011_user_engagement_fields`
- Resolve dry-run: passed
- Apply: passed
- Verify: passed

## Backup, Restore, And Rollback Drill

SQLite isolated backup/restore drill:

```powershell
.\venv\Scripts\python.exe scripts\backup_restore_drill.py --json
```

Result:

- `ok`: true
- `backup_bytes`: 5634
- `validation`: ok
- `restored_drill_rows`: 1

MySQL staging dump:

```powershell
docker compose exec -T mysql sh -lc 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysqldump -uroot --single-transaction --no-tablespaces "$MYSQL_DATABASE" > /tmp/picks_dump.sql && ls -l /tmp/picks_dump.sql'
```

Result:

- Dump path: `/tmp/picks_dump.sql`
- Dump size: 44487 bytes

MySQL isolated restore and rollback drill:

```powershell
docker compose cp scripts\maintenance\mysql_restore_check.sh mysql:/tmp/mysql_restore_check.sh
docker compose exec -T mysql sh -lc "sed -i 's/\r$//' /tmp/mysql_restore_check.sh && sh /tmp/mysql_restore_check.sh /tmp/picks_dump.sql restore_check"
```

Result:

- Restored `picks` rows in `restore_check`: 7
- Restored `legacy_payload_json IS NOT NULL` rows: 7
- Restored `auto_scan` migrated rows: 6
- Restored duplicate key groups: 0
- Restored orphan strategy rows: 0
- Restored non-default tenant rows: 0

The rollback drill restored the dump into an isolated `restore_check` database.
The primary staging database was not overwritten.

## Cutover Gate

Staging migration prerequisites for the SQLite-to-MySQL picks cutover are now
green:

- Strategy mapping and target preconditions are clean.
- Apply is gated and repeatable.
- Reconciliation has no missing rows or field mismatches.
- Source and target row counts match for the migrated slice.
- Default `tenant_id=1` is preserved for all migrated rows.
- Duplicate key handling is verified by both apply result and SQL grouping.
- `strategy_id` references resolve to existing MySQL strategies.
- SQLite and MySQL restore drills passed.

Before production cutover, freeze this report with the production SQLite
fingerprint, run the same commands against production staging data, keep the
latest validated MySQL dump, and schedule a soak window for the MySQL read/write
path before removing SQLite compatibility branches.
