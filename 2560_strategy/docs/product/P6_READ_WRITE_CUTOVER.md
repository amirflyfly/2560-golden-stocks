# P6 Picks Read/Write Cutover

Date: 2026-05-04

## Scope

This document records the first real read/write cutover step for picks. It does
not declare all SQLite usage retired. It only covers the picks repository path
used by the v1 picks API, report summary, and retained legacy picks endpoints.

## Delivered

- `backend/repositories/picks_repo.py` now supports a switchable repository backend.
- `PICKS_REPOSITORY_BACKEND=mysql` routes picks read/write calls to SQLAlchemy/MySQL.
- `PICKS_REPOSITORY_BACKEND=sqlite` keeps the existing SQLite path available for local tests and legacy maintenance.
- `PICKS_REPOSITORY_BACKEND=auto` uses MySQL in `APP_ENV=production` and SQLite outside production.
- The repository keeps returning the legacy row-shaped dict expected by existing services.
- MySQL compatibility covers create, unique-key update, review update, list filters, count, report summary aggregation, watch/archive/batch operations, and legacy payload preservation.
- MySQL `legacy_payload_json` values are decoded before returning rows to services.

## Contract Preserved

The v1 API output contract remains unchanged:

- `POST /api/v1/picks`
- `GET /api/v1/picks`
- `PATCH /api/v1/picks/{id}/review`
- `GET /api/v1/picks/{id}/timeline`
- `GET /api/v1/reports/summary`

The repository still exposes legacy field names internally, including:

- `code`
- `name`
- `pick_date`
- `strategy_name`
- `review_status`
- `result_grade`
- `reason_tag`
- `note`
- `fallback_used`

This avoids a broad service-layer rewrite during the cutover.

## Verification

Local compatibility verification:

```powershell
.\venv\Scripts\python.exe -m py_compile backend\repositories\picks_repo.py
.\venv\Scripts\python.exe -m pytest tests\test_api_v1.py tests\test_api_v1_e2e.py tests\test_app.py -q -p no:cacheprovider
```

Result: 91 passed.

Docker Compose MySQL verification:

```powershell
docker compose up -d mysql redis
docker compose run --rm -e MARKET_DATA_PROVIDER=mootdx -e MARKET_DATA_FALLBACKS=akshare -e ALLOW_MOCK_MARKET_DATA=0 backend python -m alembic upgrade head
docker compose run --rm -e MARKET_DATA_PROVIDER=mootdx -e MARKET_DATA_FALLBACKS=akshare -e ALLOW_MOCK_MARKET_DATA=0 backend python scripts/bootstrap_mysql_seed.py
docker compose run --rm -e MARKET_DATA_PROVIDER=mootdx -e MARKET_DATA_FALLBACKS=akshare -e ALLOW_MOCK_MARKET_DATA=0 backend python scripts/validate_mysql_schema.py
```

Result: schema and seed validation passed.

MySQL smoke test was run with:

```powershell
PICKS_REPOSITORY_BACKEND=mysql
```

Covered behavior:

- create pick
- duplicate create updates the same row
- review update writes status, deal status, return, risk, watch flag, and validated timestamp
- list filters by source and date
- report summary can aggregate MySQL-backed picks
- `legacy_payload_json` preserves legacy fields
- smoke row cleanup succeeds

Result: passed.

## Remaining Work

- Move startup-time SQLite `ensure_schema()` out of production app boot. Done for production by default; set `INIT_SQLITE_SCHEMA=1` only for explicit legacy maintenance.
- Migrate or retire remaining SQLite repositories outside picks, auth/session, and audit logs, including settings, strategy pool, and legacy page support paths.
- Add a production runbook note that `PICKS_REPOSITORY_BACKEND=mysql` is the explicit production setting during the transition.
- After remaining repositories move, remove the SQLite compatibility path from `picks_repo.py`.

## Auth And Session Cutover Update

Date: 2026-05-04

Delivered:

- Added Alembic revision `0004_user_sessions`.
- Added SQLAlchemy `UserSession` model.
- Updated MySQL schema validator to require the `sessions` table and revision `0004_user_sessions`.
- `backend/repositories/users_repo.py` now supports `AUTH_REPOSITORY_BACKEND=mysql`.
- `backend/repositories/sessions_repo.py` now supports `AUTH_REPOSITORY_BACKEND=mysql`.
- The MySQL auth repository preserves the current service contract by returning `role` and `is_active` compatibility fields.
- Missing non-admin tenant roles are created on demand when users are created or tenant bindings are updated.

Verified:

```powershell
.\venv\Scripts\python.exe -m py_compile backend\repositories\users_repo.py backend\repositories\sessions_repo.py backend\db\models\tenant.py
.\venv\Scripts\python.exe -m pytest tests\test_api_v1.py tests\test_api_v1_e2e.py tests\test_stage9_api.py -q -p no:cacheprovider
docker compose run --rm -e MARKET_DATA_PROVIDER=mootdx -e MARKET_DATA_FALLBACKS=akshare -e ALLOW_MOCK_MARKET_DATA=0 backend python -m alembic upgrade head
docker compose run --rm -e MARKET_DATA_PROVIDER=mootdx -e MARKET_DATA_FALLBACKS=akshare -e ALLOW_MOCK_MARKET_DATA=0 backend python scripts\validate_mysql_schema.py
```

Result:

- Focused auth/admin/API tests: 67 passed.
- MySQL schema validator: passed at `0004_user_sessions`.
- MySQL auth/session smoke: create tenant, create user, bind tenant, update role, login, read session, inactive-user session revocation, cleanup.

## Audit Log Cutover Update

Date: 2026-05-04

Delivered:

- Added Alembic revision `0005_audit_logs`.
- Added SQLAlchemy `AuditLog` model.
- Updated MySQL schema validator to require the `audit_logs` table and revision `0005_audit_logs`.
- `backend/repositories/audit_logs_repo.py` now supports `AUDIT_REPOSITORY_BACKEND=mysql`.
- Audit integrity hash generation and returned log shape are preserved.

Verified:

```powershell
.\venv\Scripts\python.exe -m py_compile backend\repositories\audit_logs_repo.py backend\db\models\tenant.py
.\venv\Scripts\python.exe -m pytest tests\test_api_v1.py tests\test_stage9_api.py tests\test_schema_alignment.py -q -p no:cacheprovider
docker compose run --rm -e MARKET_DATA_PROVIDER=mootdx -e MARKET_DATA_FALLBACKS=akshare -e ALLOW_MOCK_MARKET_DATA=0 backend python -m alembic upgrade head
docker compose run --rm -e MARKET_DATA_PROVIDER=mootdx -e MARKET_DATA_FALLBACKS=akshare -e ALLOW_MOCK_MARKET_DATA=0 backend python scripts\validate_mysql_schema.py
```

Result:

- Focused audit/API/schema tests: 63 passed.
- MySQL schema validator: passed at `0005_audit_logs`.
- MySQL audit smoke: insert, filter by tenant/action, decode detail, expose integrity hash, cleanup.

## Production SQLite Startup Guard

Date: 2026-05-04

Delivered:

- `create_app()` no longer initializes the SQLite schema by default in production.
- Development and tests keep the existing SQLite initialization behavior.
- `INIT_SQLITE_SCHEMA=1` can explicitly re-enable SQLite schema initialization for legacy maintenance.

Verified:

```powershell
.\venv\Scripts\python.exe -m py_compile backend\__init__.py
.\venv\Scripts\python.exe -m pytest tests\test_deployment_config.py tests\test_api_v1.py tests\test_stage9_api.py -q -p no:cacheprovider
```

Result:

- Focused deployment/API tests: 64 passed.
- Docker Compose production-mode `create_app()` smoke passed with `PICKS_REPOSITORY_BACKEND=mysql`, `AUTH_REPOSITORY_BACKEND=mysql`, and `AUDIT_REPOSITORY_BACKEND=mysql`.

## Legacy Repository And Service Cutover Update

Date: 2026-05-04

Delivered:

- Added Alembic revisions:
  - `0006_ui_settings_saved_filters`
  - `0007_operation_logs`
  - `0008_strategy_pool_backtests`
  - `0009_strategy_legacy_fields`
- Added SQLAlchemy models for `UiSetting`, `SavedFilter`, `OperationLog`, `StrategyPool`, and `BacktestResult`.
- Added legacy management fields on MySQL `strategies`: `is_active` and `sort_order`.
- Updated MySQL schema validator expected revision to `0009_strategy_legacy_fields`.
- `settings_repo.py` now supports `SETTINGS_REPOSITORY_BACKEND=mysql/sqlite/auto`.
- `logs_repo.py` now supports `LOGS_REPOSITORY_BACKEND=mysql/sqlite/auto`.
- `strategy_pool_repo.py` now supports `STRATEGY_POOL_REPOSITORY_BACKEND=mysql/sqlite/auto`.
- `strategy_repo.py` now supports `STRATEGY_REPOSITORY_BACKEND=mysql/sqlite/auto`.
- Removed service/page direct SQLite reads from:
  - user management page and password reset
  - deal review page
  - reports service
  - leaderboard service
  - CSV import service
  - dashboard aggregation service
  - backup validation cache
- Non-repository direct `backend.repositories.db` imports are now limited to the guarded startup SQLite initialization path and legacy backup file path constants have been moved out of the SQLite helper.

Verified:

```powershell
.\venv\Scripts\python.exe -m pytest tests\test_api_v1.py tests\test_stage9_api.py tests\test_schema_alignment.py -q -p no:cacheprovider
docker compose build backend
docker compose run --rm -e MARKET_DATA_PROVIDER=mootdx -e MARKET_DATA_FALLBACKS=akshare -e ALLOW_MOCK_MARKET_DATA=0 backend python -m alembic upgrade head
docker compose run --rm -e MARKET_DATA_PROVIDER=mootdx -e MARKET_DATA_FALLBACKS=akshare -e ALLOW_MOCK_MARKET_DATA=0 backend python scripts/validate_mysql_schema.py
```

Result:

- Focused API/schema tests: 75 passed.
- MySQL schema validator: passed at `0009_strategy_legacy_fields`.
- MySQL smoke tests passed for settings, operation logs, strategy pool/backtests, and strategy management.

## SQLite Data Migration Expansion

Date: 2026-05-04

Delivered:

- `scripts/migrate_sqlite_to_mysql.py` now plans auxiliary legacy tables in dry-run output:
  - `strategies`
  - `ui_settings`
  - `saved_filters`
  - `operation_logs`
  - `strategy_pools`
  - `backtest_results`
- `--apply` now migrates auxiliary legacy tables after the picks apply gate passes.
- Auxiliary migration is idempotent by natural key:
  - `strategies`: `tenant_id + code`
  - `ui_settings`: `setting_key`
  - `saved_filters`: `name + query_string`
  - `operation_logs`: `created_at + action + target_ids + detail`
  - `strategy_pools`: `strategy_code + code`
  - `backtest_results`: `strategy_code + start_date + end_date + backtest_date`
- `scripts/staging_mysql_migration.py` now surfaces auxiliary plan/apply details in stage output.
- Migration tests now cover auxiliary table planning, field mapping, and repeatable apply behavior.

Verified:

```powershell
.\venv\Scripts\python.exe -m pytest tests\test_sqlite_to_mysql_migration.py tests\test_staging_mysql_migration.py -q -p no:cacheprovider
.\venv\Scripts\python.exe scripts\migrate_sqlite_to_mysql.py --json
```

Result:

- Migration tests: 19 passed.
- Local dry-run generated auxiliary counts for the current SQLite database without mutating it.
- Docker Compose MySQL apply + reconciliation passed; a second apply completed idempotently with picks existing=6, operation_logs existing=57, strategy_pools existing=5, backtest_results existing=4.

## Research Report Cutover Update

Date: 2026-05-04

Delivered:

- Added Alembic revision `0010_research_reports`.
- Added SQLAlchemy `ResearchReport` model.
- Updated MySQL schema validator to require `research_reports`, its indexes, and unique key `pick_id + analysis_date`.
- `picks_repo.update_research_snapshot()` now writes research report history in MySQL mode.
- SQLite-to-MySQL migration now includes legacy `research_reports` as an auxiliary table.

Verified:

```powershell
.\venv\Scripts\python.exe -m pytest tests\test_schema_alignment.py tests\test_sqlite_to_mysql_migration.py -q -p no:cacheprovider
docker compose run --rm -e MARKET_DATA_PROVIDER=mootdx -e MARKET_DATA_FALLBACKS=akshare -e ALLOW_MOCK_MARKET_DATA=0 backend python -m alembic upgrade head
docker compose run --rm -e MARKET_DATA_PROVIDER=mootdx -e MARKET_DATA_FALLBACKS=akshare -e ALLOW_MOCK_MARKET_DATA=0 backend python scripts/validate_mysql_schema.py
```

Result:

- Focused schema/migration tests: 36 passed.
- MySQL schema validator: passed at `0010_research_reports`.
- MySQL research report smoke: update snapshot, list reports by pick, and latest report map passed.
- Docker Compose migration apply migrated legacy `research_reports` inserted=1; second apply reported existing=1.

## Runtime SQLite Dependency Guard

Date: 2026-05-04

Delivered:

- Added a repo hygiene test that blocks direct `backend.repositories.db` imports from non-repository runtime modules.
- Allowed imports are limited to dual-backend repositories and the guarded app startup SQLite initialization path.

Verified:

```powershell
.\venv\Scripts\python.exe -m pytest tests\test_repo_hygiene.py -q -p no:cacheprovider
```

Result:

- Repo hygiene tests: 4 passed.

## Production Repository Backend Guard

Date: 2026-05-04

Delivered:

- `.env.example` now pins all production repository backends to MySQL:
  - `PICKS_REPOSITORY_BACKEND`
  - `AUTH_REPOSITORY_BACKEND`
  - `AUDIT_REPOSITORY_BACKEND`
  - `SETTINGS_REPOSITORY_BACKEND`
  - `LOGS_REPOSITORY_BACKEND`
  - `STRATEGY_POOL_REPOSITORY_BACKEND`
  - `STRATEGY_REPOSITORY_BACKEND`
- `docker-compose.yml` defaults the same repository backend variables to `mysql` for the backend service.
- `Settings.from_env()` rejects explicit SQLite or unknown repository backend values when `APP_ENV=production`.
- `scripts/deploy_preflight.py` now fails if the production env template or compose baseline does not expose MySQL repository backends.

Verified:

```powershell
.\venv\Scripts\python.exe -m pytest tests\test_deploy_preflight.py tests\test_deployment_config.py -q -p no:cacheprovider
```

Result:

- Production preflight/config tests: 11 passed.

## Production Runtime Hardening Update

Date: 2026-05-04

Delivered:

- Added Alembic revision `0011_user_engagement_fields`.
- Added MySQL `users.points` and `users.last_checkin` fields so `/user/checkin` no longer silently drops points/check-in state in MySQL mode.
- `users_repo.update_user_points()`, `get_user_last_checkin()`, and `update_user_last_checkin()` now support `AUTH_REPOSITORY_BACKEND=mysql`.
- `users_repo.create_user()` now normalizes duplicate username failures into `DuplicateUserError`; `AdminApiService` no longer catches SQLite-only integrity errors.
- Legacy SQLite backup/restore service now raises in production for backup creation, restore, validation, and restore upload paths.
- `web_panel.py` now hard-fails when `APP_ENV=production` because it is a legacy SQLite entrypoint.
- `start.sh` and `start_flask.sh` now refuse production mode and point operators to Docker Compose.
- `/api/v1/health` and monitoring database health now expose effective repository backends and database dialect.
- `scripts/deploy_preflight.py` now checks an actual `.env` when present for:
  - production `APP_ENV`
  - `INIT_SQLITE_SCHEMA` not enabled
  - non-SQLite `DATABASE_URL`
  - repository backends not forced to SQLite
- CI now includes a production MySQL smoke job that starts MySQL/Redis, runs preflight, applies Alembic, seeds baseline data, and validates schema.

Verified:

```powershell
.\venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
npm test
npm run repo:hygiene
docker compose config --quiet
docker compose build backend
docker compose run --rm -e MARKET_DATA_FALLBACKS=akshare -e ALLOW_MOCK_MARKET_DATA=0 backend python -m alembic upgrade head
docker compose run --rm -e MARKET_DATA_FALLBACKS=akshare -e ALLOW_MOCK_MARKET_DATA=0 backend python scripts/bootstrap_mysql_seed.py
docker compose run --rm -e MARKET_DATA_FALLBACKS=akshare -e ALLOW_MOCK_MARKET_DATA=0 backend python scripts/validate_mysql_schema.py
docker compose cp scripts\maintenance\mysql_restore_check.sh mysql:/tmp/mysql_restore_check.sh
docker compose exec -T mysql sh -lc "MYSQL_PWD=\"$MYSQL_ROOT_PASSWORD\" mysqldump -uroot --single-transaction --routines --triggers --default-character-set=utf8mb4 --no-tablespaces \"$MYSQL_DATABASE\" > /tmp/strategy_dump.sql && sed -i 's/\r$//' /tmp/mysql_restore_check.sh && sh /tmp/mysql_restore_check.sh /tmp/strategy_dump.sql restore_check_ci"
```

Result:

- Full Python tests: 174 passed.
- Frontend build: passed.
- Repo hygiene: violations 0.
- Production preflight: 27 checks passed.
- MySQL schema validator: passed at `0011_user_engagement_fields`.
- MySQL user check-in smoke: create user, add points, set last check-in, read back, cleanup passed.
- MySQL dump/restore check: restored into isolated `restore_check_ci` database and verified picks counts.

## Production SQLite Retirement Hardening Update

Date: 2026-05-04

Delivered:

- Production configuration now hard-rejects `INIT_SQLITE_SCHEMA=1`; SQLite schema initialization is never allowed during production app startup.
- Production configuration rejects insecure secrets, weak database passwords, mock market providers/fallbacks, SQLite database URLs, and explicit SQLite repository backends.
- Added `Settings.effective_repository_backends()` so health and readiness checks expose the actual repository backend contract in one place.
- Added `/api/v1/readiness` for production load balancers and Docker health checks.
- The readiness check verifies:
  - app configuration can be loaded
  - SQLAlchemy database connectivity through `SELECT 1`
  - Alembic schema revision equals `0011_user_engagement_fields` in production
  - Redis/cache health
  - every repository backend resolves away from SQLite in production
- Dockerfile health check now calls `/api/v1/readiness`.
- Dockerfile now sets `APP_ENV=production`, so direct image execution fails production preflight instead of silently booting development/SQLite defaults.
- Docker build context now excludes `vendor/` so embedded third-party demos, SQLite files, logs, and alternate APIs are not copied into the production image.
- CI production smoke now starts the Compose stack and checks readiness over HTTP.
- CI production smoke now also asserts the frontend gateway returns HTTP 410 for legacy `/api/picks`.
- Legacy admin SQLite backup/restore write routes are frozen in production with HTTP 410:
  - `POST /admin/backups/create`
  - `DELETE /admin/backups/<name>`
  - `POST /admin/restore`
  - `POST /admin/backup-key`
- Legacy `/api` write routes are frozen in production with HTTP 410, including picks create/update/delete, archive/unarchive, batch review operations, CSV bulk import, saved filters, dashboard order, and stock-data saves.
- Legacy main-page write routes such as `/user/checkin` are frozen in production before auth/session repository access.
- Legacy strategy write routes are frozen in production with HTTP 410, including strategy pool add/remove, scan add-to-pool, strategy scans, manual strategy run/backtest POSTs, and legacy strategy CRUD pages.
- The frontend Nginx production gateway only proxies `/api/v1/` to the backend and returns HTTP 410 for the legacy `/api/` prefix.
- `BackupService` disables legacy SQLite backup creation, restore, upload validation, and validation-cache writes in production.
- Legacy backup and migration-check pages render an explicit disabled state in production instead of exposing SQLite operations.
- `web_panel.py`, `start.sh`, and `start_flask.sh` refuse production mode and point operators to Docker Compose; `web_panel.py` now uses the shared legacy SQLite guard so `APP_ENV` and `FLASK_ENV` are both covered.
- Added `scripts/maintenance/legacy_sqlite_guard.py` and wired it into legacy SQLite maintenance scripts so ad hoc SQLite jobs fail closed when `APP_ENV` or `FLASK_ENV` is production.
- `scheduler.py` now refuses production mode because it is a legacy SQLite/CSV scheduler.
- Root-level offline SQLite/CSV scripts now also refuse production mode:
  - `content_analytics.py`
  - `daily_review_brief.py`
  - `first_limit_replay.py`
  - `first_limit_validate.py`
  - `leaderboards.py`
  - `master_ledger.py`
  - `report_2560.py`
  - `review_metrics.py`
  - `run_2560_backtest.py`
  - `strategy_2560.py`
  - `strategy_digest.py`
  - `strategy_lite.py`
  - `ui_demo.py`
- Default admin bootstrap no longer swallows user creation failures in production.
- MySQL research report paths now fail closed if `research_reports` is unavailable instead of returning empty/zero results.
- v1 report create/list/detail now persists through `research_reports` instead of returning placeholder in-memory payloads.
- The legacy SQLite helper itself now refuses production mode, so accidental direct imports fail closed.
- Local agent skill/tool cache directories are ignored to keep audits focused on application code.
- MySQL user parity now includes admin tenant binding repair and user engagement fields (`points`, `last_checkin`).
- MySQL strategy summary now derives `worthy_total` from MySQL strategy ids and pick status instead of relying on legacy JSON review status.
- v1 admin user audit details no longer pass raw password values; callers now record `password_set`.
- `.env` no longer uses mock market-data fallback.
- Production preflight now fails if critical v1/API, MySQL repository, Alembic, frontend gateway, CI, test, and P6 runbook files exist locally but are not tracked by Git.
- Deployment config tests now include a WSGI entrypoint import smoke for `app:app` and assert `/api/v1/readiness` is registered.
- Product closure pass added Dashboard candidate/scan/failed-task metrics, K-line pool context, report drilldowns, and backtest portfolio/risk attribution fields.

Verified:

```powershell
.\venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
npm test
npm run repo:hygiene
npm run repo:clean-index -- --limit 10
docker compose config --quiet
docker compose build backend
docker compose build frontend
docker compose up -d mysql redis backend frontend
Invoke-WebRequest http://localhost:5174/api/v1/readiness
Invoke-WebRequest http://localhost:5174/api/picks -Method Post -ContentType application/json -Body '{}'
docker compose run --rm -e MARKET_DATA_FALLBACKS=akshare -e ALLOW_MOCK_MARKET_DATA=0 backend python scripts/validate_mysql_schema.py
```

Result:

- Full Python tests: 194 passed.
- Frontend build: passed.
- Repo hygiene: violations 0.
- Repo clean-index dry run: candidates 0.
- Production preflight: 33 checks passed, including `git:critical-files-tracked`.
- Docker Compose config: passed.
- Backend and frontend image builds: passed.
- Compose runtime: MySQL, Redis, backend, and frontend healthy.
- Readiness endpoint returned `ready: true`, `database.dialect: mysql`, schema revision `0011_user_engagement_fields`, `cache.redis`, and all repository backends as `mysql`.
- Legacy API gateway returned HTTP 410 for `/api/*` through the production frontend, and CI now enforces that behavior.
- MySQL schema validator: passed at `0011_user_engagement_fields`.

Remaining P6 hardening backlog:

- Audit root-level report/research scripts that still read local SQLite/CSV artifacts and either move them under guarded maintenance or document them as offline-only tools.
- After a full production soak, remove SQLite compatibility branches from dual-backend repositories instead of only guarding them.
