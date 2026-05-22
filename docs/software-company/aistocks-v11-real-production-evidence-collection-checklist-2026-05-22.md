# AiStocks v1.1 Real Production Evidence Collection Checklist — 2026-05-22

## 0. Scope and Safety Boundary

This document is a pre-execution checklist and command template for collecting real staging/production evidence for AiStocks v1.1. It is prepared from:

- `D:/AiStocks/docs/software-company/aistocks-v11-production-evidence-execution-plan-2026-05-21.md`
- `D:/AiStocks/docs/software-company/aistocks-v11-production-evidence-local-precheck-2026-05-22.md`
- `scripts/production_evidence.py --help`

Safety boundary:

- Do not connect to real staging/production until the user explicitly confirms the target environment and execution window.
- Do not send external push messages until the user explicitly confirms the push test channel and recipient scope.
- Do not write or mutate business data outside the approved test tenant/account and approved test symbols.
- Do not mark GO from local precheck alone.
- Do not embed secrets, passwords, tokens, cookies, or full database credentials in this document, shell history, screenshots, logs, or evidence JSON.

Current known local precheck status:

- Local `deploy_preflight.py` passed: `ok=true`, `61/61`.
- Local `check_repo_hygiene.py --json` passed: `ok=true`, `405` paths, `0` violations.
- Example evidence validation failed as expected: `production evidence failed: 23 checks` because `docs/product/PRODUCTION_EVIDENCE.example.json` is not real production evidence.
- `D:/AiStocks/venv/Scripts/python.exe` was absent in the local Git Bash environment; system Python 3.12.10 was used for safe local checks.
- Git short hash observed during local precheck: `465525e`; release evidence must be tied to the final approved release commit/artifact, not an arbitrary dirty working tree.

## 1. Information Required Before Execution

The following information must be provided and approved before running real staging/production evidence collection.

| Category | Required value | Placeholder | Owner | Confirmation required |
| --- | --- | --- | --- | --- |
| Target environment | `staging`, `preprod`, or `production` | `<TARGET_ENV>` | Release owner | Yes |
| Base URL | Public HTTPS entry for frontend/API | `<BASE_URL>` | Environment owner | Yes |
| API base URL | API root if different from frontend | `<API_BASE_URL>` | Environment owner | Yes |
| Execution window | Approved start/end time and timezone | `<EXECUTION_WINDOW>` | Release owner | Yes |
| Release commit | Git commit hash to validate | `<RELEASE_COMMIT>` | Release owner | Yes |
| Release artifact | Image tag, build ID, package URL, or deployment revision | `<RELEASE_ARTIFACT>` | Release/DevOps owner | Yes |
| Test tenant | Tenant/org id or slug dedicated to release validation | `<TEST_TENANT_ID>` | Product/Environment owner | Yes |
| Test account | Username/email with release validation permissions | `<TEST_ACCOUNT>` | Product/Environment owner | Yes |
| Auth method | Session cookie, bearer token, SSO, MFA procedure, or approved manual browser login flow | `<AUTH_METHOD>` | Security/Product owner | Yes |
| Credential handoff | Secure channel where executor can obtain temporary credentials | `<CREDENTIAL_HANDOFF_CHANNEL>` | Security owner | Yes |
| Test symbols/universe | Approved symbols and scan universe for validation | `<TEST_SYMBOLS>` | Product owner | Yes |
| Market data provider | Production/staging data provider and fallback policy | `<MARKET_DATA_PROVIDER>` | Data owner | Yes |
| Push test channel | Dedicated test webhook/group/recipient, never a customer channel | `<PUSH_TEST_CHANNEL>` | Product/Operations owner | Yes |
| Delivery query method | API endpoint, admin page, or DB query path for delivery records | `<DELIVERY_QUERY_METHOD>` | Backend/Operations owner | Yes |
| Log system | Log platform URL/query syntax/index/service names | `<LOG_SYSTEM_URL>` / `<LOG_QUERY_TEMPLATE>` | DevOps owner | Yes |
| DB read-only access | Read-only connection method or approved query console | `<DB_READONLY_ACCESS>` | DBA/DevOps owner | Yes |
| Evidence directory | Local or shared path for JSON, screenshots, logs, SQL exports | `<EVIDENCE_DIR>` | Release owner | Yes |
| Evidence bundle path | Final production evidence JSON path | `<EVIDENCE_JSON>` | Release owner | Yes |
| Rollback owner | Named owner who can trigger rollback/stop workers/disable push | `<ROLLBACK_OWNER>` | Release owner | Yes |
| GO/NO-GO approver | Named approver for final judgment | `<GO_NOGO_APPROVER>` | Release owner | Yes |

## 2. Required Evidence Items

Each item must be collected with request time, actor/test account, target environment, release commit/artifact, API/page response, logs, and where applicable DB records and screenshots.

| # | Evidence item | Minimum proof | Output artifact placeholders | Explicit confirmation needed before execution |
| --- | --- | --- | --- | --- |
| 1 | Health check | `GET /health`, `GET /api/v1/health`, and/or `GET /api/v1/readiness` return 200 and dependency status is acceptable. | `<EVIDENCE_DIR>/01-health-response.json`, `<EVIDENCE_DIR>/01-health-logs.txt` | Confirm target environment and read-only checks. |
| 2 | Login and `/api/v1/me` | Test account logs in successfully; user, tenant, and role are correct. | `<EVIDENCE_DIR>/02-login-screenshot.png`, `<EVIDENCE_DIR>/02-me-response.json`, `<EVIDENCE_DIR>/02-auth-logs.txt` | Confirm test account, auth method, and screenshot redaction rules. |
| 3 | Market synchronization | Market sync task can be triggered, tracked to terminal state, and produces acceptable data/source/quality metadata. | `<EVIDENCE_DIR>/03-market-sync-create.json`, `<EVIDENCE_DIR>/03-market-sync-task.json`, `<EVIDENCE_DIR>/03-market-sync-db.csv`, `<EVIDENCE_DIR>/03-market-sync-screenshot.png` | Confirm triggering sync is allowed and approved symbols/date range. |
| 4 | Strategy scan | Scan can be created and completed; results include strategy, explainability, data quality, runner metadata, and at least one usable signal if expected. | `<EVIDENCE_DIR>/04-scan-create.json`, `<EVIDENCE_DIR>/04-scan-results.json`, `<EVIDENCE_DIR>/04-scan-db.csv`, `<EVIDENCE_DIR>/04-scan-screenshot.png` | Confirm scan parameters and allowed test universe. |
| 5 | Paper trading `apply-signal` | A selected executable scan signal creates/updates paper order, trade, or position records in the approved test tenant. | `<EVIDENCE_DIR>/05-apply-signal-request.json`, `<EVIDENCE_DIR>/05-apply-signal-response.json`, `<EVIDENCE_DIR>/05-paper-trading-db.csv`, `<EVIDENCE_DIR>/05-paper-trading-screenshot.png` | Confirm mutation of test tenant paper trading data. |
| 6 | Paper trading `evaluate-exits` | Exit evaluation runs and returns structured results, including a valid no-exit response if no exit condition is met. | `<EVIDENCE_DIR>/06-evaluate-exits-response.json`, `<EVIDENCE_DIR>/06-evaluate-exits-task.json`, `<EVIDENCE_DIR>/06-evaluate-exits-db.csv`, `<EVIDENCE_DIR>/06-evaluate-exits-screenshot.png` | Confirm mutation/evaluation against test tenant paper positions. |
| 7 | Daily report generation and push | Daily report workflow creates a report/delivery and sends only to the approved test channel. | `<EVIDENCE_DIR>/07-daily-report-response.json`, `<EVIDENCE_DIR>/07-daily-report-delivery.json`, `<EVIDENCE_DIR>/07-push-receiver-screenshot.png` | Confirm external push test channel and message content. |
| 8 | Delivery query | Delivery detail/list can be queried by delivery id, report task id, channel id, or time range; result includes status, response code/error, retry count, and redacted payload summary. | `<EVIDENCE_DIR>/08-delivery-query-response.json`, `<EVIDENCE_DIR>/08-delivery-db.csv` | Confirm delivery query method and redaction rules. |
| 9 | Application/worker/access logs | Logs correlate every step by timestamp, request id, task id, scan id, signal id, delivery id. | `<EVIDENCE_DIR>/09-api-logs.txt`, `<EVIDENCE_DIR>/09-worker-logs.txt`, `<EVIDENCE_DIR>/09-error-logs.txt` | Confirm log platform query access and export policy. |
| 10 | Database records | Read-only SQL/export proves tasks, scans, signals, paper orders/positions, reports, and deliveries exist and match API ids. | `<EVIDENCE_DIR>/10-db-records/*.csv` | Confirm DB read-only access and approved query fields. |
| 11 | Screenshots | Browser screenshots show login success, market sync/task page, scan result page, paper trading page, daily report/push page, receiver message page. | `<EVIDENCE_DIR>/screenshots/*.png` | Confirm screenshots can be taken and sensitive fields are masked. |
| 12 | Production evidence JSON | Final JSON bundle passes `scripts/production_evidence.py --evidence <EVIDENCE_JSON>` with required gates. | `<EVIDENCE_JSON>`, `<EVIDENCE_DIR>/production-evidence-validation.json` | Confirm final bundle contents and GO/NO-GO approver. |

## 3. Command Templates With Placeholders

The following templates intentionally use placeholders. Replace placeholders only after user confirmation. Do not paste secrets directly into commands; use a secure secret manager, short-lived environment variables, or an approved credential handoff process.

### 3.1 Local script/template preparation

```bash
# Show CLI help; safe/read-only.
python "D:/AiStocks/scripts/production_evidence.py" --help

# Create a blank evidence template; safe file generation only.
python "D:/AiStocks/scripts/production_evidence.py" \
  --write-template "<EVIDENCE_DIR>/production-evidence-template.json"

# Create a local runtime/readiness sample from current environment only after confirming it will not hit real external targets.
python "D:/AiStocks/scripts/production_evidence.py" \
  --write-readiness-sample "<EVIDENCE_DIR>/readiness-sample-local.json"

# Create a draft bundle with current readiness sample embedded, if approved.
python "D:/AiStocks/scripts/production_evidence.py" \
  --write-runtime-bundle "<EVIDENCE_DIR>/production-evidence-draft.json"

# Validate the final evidence JSON after all real evidence is inserted.
python "D:/AiStocks/scripts/production_evidence.py" \
  --evidence "<EVIDENCE_JSON>" \
  --min-soak-minutes "<MIN_SOAK_MINUTES>"
```

### 3.2 Common environment variables for curl/API capture

```bash
export TARGET_ENV="<TARGET_ENV>"
export BASE_URL="<BASE_URL>"
export API_BASE_URL="<API_BASE_URL>"
export EVIDENCE_DIR="<EVIDENCE_DIR>"
export RELEASE_COMMIT="<RELEASE_COMMIT>"
export RELEASE_ARTIFACT="<RELEASE_ARTIFACT>"
export TEST_TENANT_ID="<TEST_TENANT_ID>"
export TEST_ACCOUNT="<TEST_ACCOUNT>"

# Use a secure handoff. Do not hard-code tokens in files or shell history.
export AUTH_HEADER="Authorization: Bearer <SHORT_LIVED_TOKEN>"
export REQUEST_ID_PREFIX="evidence-<YYYYMMDDHHMMSS>"
```

### 3.3 Health check

```bash
curl -sS -D "${EVIDENCE_DIR}/01-health-headers.txt" \
  -H "X-Request-ID: ${REQUEST_ID_PREFIX}-health" \
  "${API_BASE_URL}/health" \
  -o "${EVIDENCE_DIR}/01-health-response.json"

curl -sS -D "${EVIDENCE_DIR}/01-readiness-headers.txt" \
  -H "X-Request-ID: ${REQUEST_ID_PREFIX}-readiness" \
  "${API_BASE_URL}/api/v1/readiness" \
  -o "${EVIDENCE_DIR}/01-readiness-response.json"
```

### 3.4 Login/session verification

```bash
# If bearer/session is obtained manually through approved login flow, verify current user.
curl -sS -D "${EVIDENCE_DIR}/02-me-headers.txt" \
  -H "${AUTH_HEADER}" \
  -H "X-Request-ID: ${REQUEST_ID_PREFIX}-me" \
  "${API_BASE_URL}/api/v1/me" \
  -o "${EVIDENCE_DIR}/02-me-response.json"
```

Manual browser evidence to capture after confirmed login:

- `<EVIDENCE_DIR>/screenshots/02-login-success.png`
- `<EVIDENCE_DIR>/screenshots/02-dashboard.png`

### 3.5 Market sync

```bash
curl -sS -D "${EVIDENCE_DIR}/03-market-sync-create-headers.txt" \
  -X POST \
  -H "${AUTH_HEADER}" \
  -H "Content-Type: application/json" \
  -H "X-Request-ID: ${REQUEST_ID_PREFIX}-market-sync" \
  "${API_BASE_URL}/api/v1/market-data/sync" \
  --data @"${EVIDENCE_DIR}/requests/03-market-sync-request.json" \
  -o "${EVIDENCE_DIR}/03-market-sync-create.json"

curl -sS -D "${EVIDENCE_DIR}/03-market-sync-task-headers.txt" \
  -H "${AUTH_HEADER}" \
  -H "X-Request-ID: ${REQUEST_ID_PREFIX}-market-sync-status" \
  "${API_BASE_URL}/api/v1/tasks/<MARKET_SYNC_TASK_ID>" \
  -o "${EVIDENCE_DIR}/03-market-sync-task.json"
```

Request body template (`<EVIDENCE_DIR>/requests/03-market-sync-request.json`):

```json
{
  "tenant_id": "<TEST_TENANT_ID>",
  "symbols": ["<TEST_SYMBOL_1>", "<TEST_SYMBOL_2>"],
  "period": "<PERIOD>",
  "start_date": "<START_DATE>",
  "end_date": "<END_DATE>",
  "provider": "<MARKET_DATA_PROVIDER>",
  "dry_run": false
}
```

### 3.6 Strategy scan

```bash
curl -sS -D "${EVIDENCE_DIR}/04-scan-create-headers.txt" \
  -X POST \
  -H "${AUTH_HEADER}" \
  -H "Content-Type: application/json" \
  -H "X-Request-ID: ${REQUEST_ID_PREFIX}-scan" \
  "${API_BASE_URL}/api/v1/scans" \
  --data @"${EVIDENCE_DIR}/requests/04-scan-request.json" \
  -o "${EVIDENCE_DIR}/04-scan-create.json"

curl -sS -D "${EVIDENCE_DIR}/04-scan-detail-headers.txt" \
  -H "${AUTH_HEADER}" \
  -H "X-Request-ID: ${REQUEST_ID_PREFIX}-scan-detail" \
  "${API_BASE_URL}/api/v1/scans/<SCAN_ID>" \
  -o "${EVIDENCE_DIR}/04-scan-detail.json"

curl -sS -D "${EVIDENCE_DIR}/04-scan-results-headers.txt" \
  -H "${AUTH_HEADER}" \
  -H "X-Request-ID: ${REQUEST_ID_PREFIX}-scan-results" \
  "${API_BASE_URL}/api/v1/scans/<SCAN_ID>/results" \
  -o "${EVIDENCE_DIR}/04-scan-results.json"
```

Request body template (`<EVIDENCE_DIR>/requests/04-scan-request.json`):

```json
{
  "tenant_id": "<TEST_TENANT_ID>",
  "strategy": "<STRATEGY_NAME_OR_ID>",
  "symbols": ["<TEST_SYMBOL_1>", "<TEST_SYMBOL_2>"],
  "timeframe": "1d",
  "parameters": {
    "profile": "<APPROVED_TEST_PROFILE>"
  }
}
```

### 3.7 Paper trading `apply-signal`

```bash
curl -sS -D "${EVIDENCE_DIR}/05-apply-signal-headers.txt" \
  -X POST \
  -H "${AUTH_HEADER}" \
  -H "Content-Type: application/json" \
  -H "X-Request-ID: ${REQUEST_ID_PREFIX}-apply-signal" \
  "${API_BASE_URL}/api/v1/trading/paper/apply-signal" \
  --data @"${EVIDENCE_DIR}/requests/05-apply-signal-request.json" \
  -o "${EVIDENCE_DIR}/05-apply-signal-response.json"
```

Request body template (`<EVIDENCE_DIR>/requests/05-apply-signal-request.json`):

```json
{
  "tenant_id": "<TEST_TENANT_ID>",
  "scan_id": "<SCAN_ID>",
  "signal_id": "<SIGNAL_ID>",
  "symbol": "<TEST_SYMBOL>",
  "paper_account_id": "<PAPER_ACCOUNT_ID>",
  "idempotency_key": "<IDEMPOTENCY_KEY>"
}
```

### 3.8 Paper trading `evaluate-exits`

```bash
curl -sS -D "${EVIDENCE_DIR}/06-evaluate-exits-headers.txt" \
  -X POST \
  -H "${AUTH_HEADER}" \
  -H "Content-Type: application/json" \
  -H "X-Request-ID: ${REQUEST_ID_PREFIX}-evaluate-exits" \
  "${API_BASE_URL}/api/v1/trading/paper/evaluate-exits" \
  --data @"${EVIDENCE_DIR}/requests/06-evaluate-exits-request.json" \
  -o "${EVIDENCE_DIR}/06-evaluate-exits-response.json"
```

Request body template (`<EVIDENCE_DIR>/requests/06-evaluate-exits-request.json`):

```json
{
  "tenant_id": "<TEST_TENANT_ID>",
  "paper_account_id": "<PAPER_ACCOUNT_ID>",
  "symbols": ["<TEST_SYMBOL>"],
  "evaluation_date": "<EVALUATION_DATE>"
}
```

### 3.9 Daily report push

Endpoint names can differ by final router configuration. Confirm exact endpoint before execution.

```bash
curl -sS -D "${EVIDENCE_DIR}/07-daily-report-headers.txt" \
  -X POST \
  -H "${AUTH_HEADER}" \
  -H "Content-Type: application/json" \
  -H "X-Request-ID: ${REQUEST_ID_PREFIX}-daily-report" \
  "${API_BASE_URL}/api/v1/reports/daily/push" \
  --data @"${EVIDENCE_DIR}/requests/07-daily-report-request.json" \
  -o "${EVIDENCE_DIR}/07-daily-report-response.json"
```

Request body template (`<EVIDENCE_DIR>/requests/07-daily-report-request.json`):

```json
{
  "tenant_id": "<TEST_TENANT_ID>",
  "report_date": "<REPORT_DATE>",
  "channel_id": "<PUSH_TEST_CHANNEL_ID>",
  "recipient_scope": "test-only",
  "idempotency_key": "<IDEMPOTENCY_KEY>"
}
```

### 3.10 Delivery query

```bash
curl -sS -D "${EVIDENCE_DIR}/08-delivery-query-headers.txt" \
  -H "${AUTH_HEADER}" \
  -H "X-Request-ID: ${REQUEST_ID_PREFIX}-delivery-query" \
  "${API_BASE_URL}/api/v1/deliveries/<DELIVERY_ID>" \
  -o "${EVIDENCE_DIR}/08-delivery-query-response.json"

curl -sS -D "${EVIDENCE_DIR}/08-delivery-list-headers.txt" \
  -H "${AUTH_HEADER}" \
  -H "X-Request-ID: ${REQUEST_ID_PREFIX}-delivery-list" \
  "${API_BASE_URL}/api/v1/deliveries?tenant_id=<TEST_TENANT_ID>&channel_id=<PUSH_TEST_CHANNEL_ID>&from=<FROM_ISO8601>&to=<TO_ISO8601>" \
  -o "${EVIDENCE_DIR}/08-delivery-list-response.json"
```

### 3.11 Log exports

Use the approved log platform rather than ad hoc server access where possible. Template only:

```text
<LOG_QUERY_TEMPLATE>
service:<BACKEND_SERVICE_NAME> OR service:<WORKER_SERVICE_NAME>
env:<TARGET_ENV>
release:<RELEASE_COMMIT_OR_ARTIFACT>
request_id:${REQUEST_ID_PREFIX}-*
time:[<FROM_ISO8601> TO <TO_ISO8601>]
```

Expected exports:

- `<EVIDENCE_DIR>/09-api-logs.txt`
- `<EVIDENCE_DIR>/09-worker-logs.txt`
- `<EVIDENCE_DIR>/09-error-logs.txt`

### 3.12 DB read-only query templates

Run only through approved read-only access. Redact PII and secrets before saving.

```sql
-- Tasks created during evidence run
SELECT id, tenant_id, type, status, created_at, updated_at, error_message
FROM tasks
WHERE tenant_id = '<TEST_TENANT_ID>'
  AND created_at BETWEEN '<FROM_ISO8601>' AND '<TO_ISO8601>'
ORDER BY created_at DESC;

-- Scan and signal records
SELECT id, tenant_id, strategy, status, created_at, completed_at
FROM scan_tasks
WHERE tenant_id = '<TEST_TENANT_ID>'
  AND id = '<SCAN_ID>';

SELECT id, scan_id, tenant_id, symbol, action, confidence, created_at
FROM trading_signals
WHERE tenant_id = '<TEST_TENANT_ID>'
  AND scan_id = '<SCAN_ID>';

-- Paper trading records
SELECT id, tenant_id, paper_account_id, symbol, side, status, signal_id, created_at
FROM paper_orders
WHERE tenant_id = '<TEST_TENANT_ID>'
  AND signal_id = '<SIGNAL_ID>';

SELECT id, tenant_id, paper_account_id, symbol, quantity, average_price, updated_at
FROM paper_positions
WHERE tenant_id = '<TEST_TENANT_ID>'
  AND paper_account_id = '<PAPER_ACCOUNT_ID>';

-- Report/delivery records
SELECT id, tenant_id, report_date, status, created_at, updated_at
FROM daily_reports
WHERE tenant_id = '<TEST_TENANT_ID>'
  AND report_date = '<REPORT_DATE>';

SELECT id, tenant_id, channel_id, status, response_code, retry_count, created_at, updated_at
FROM delivery_records
WHERE tenant_id = '<TEST_TENANT_ID>'
  AND id = '<DELIVERY_ID>';
```

If actual table names differ from the deployed schema, record the exact schema/table mapping before running evidence queries.

## 4. Actions Requiring Explicit User Confirmation

Do not execute the following without explicit user confirmation in the current release context:

1. Connecting to any real staging/preproduction/production base URL.
2. Using real credentials, session cookies, bearer tokens, SSO sessions, or MFA flows.
3. Triggering market data synchronization against real providers or non-test universes.
4. Creating strategy scans in a shared tenant or on broad symbol universes.
5. Running `apply-signal`, because it writes paper trading orders/trades/positions even if no live broker is involved.
6. Running `evaluate-exits`, because it evaluates/may update paper trading state.
7. Triggering daily report generation or external push delivery.
8. Sending any message to webhook/group/email/SMS/IM endpoints, including test endpoints.
9. Querying or exporting production logs that may contain PII, secrets, or customer data.
10. Querying or exporting database records, even read-only, unless query scope and redaction rules are approved.
11. Taking screenshots of authenticated pages or receiver channels unless masking/redaction is approved.
12. Writing a final evidence JSON that claims GO status or production readiness.
13. Deleting/retiring SQLite write paths, legacy branches, or `legacy_payload_json` queries based on evidence gates.
14. Changing environment variables, feature flags, deployment config, worker state, traffic routing, or rollback state.

## 5. Evidence Run Template

Fill this section during execution after approval. Leave placeholders blank until real values are known.

| Field | Value |
| --- | --- |
| Executor | `<EXECUTOR_NAME>` |
| Execution start | `<START_ISO8601>` |
| Execution end | `<END_ISO8601>` |
| Target environment | `<TARGET_ENV>` |
| Base URL | `<BASE_URL>` |
| API base URL | `<API_BASE_URL>` |
| Release commit | `<RELEASE_COMMIT>` |
| Release artifact | `<RELEASE_ARTIFACT>` |
| Test tenant | `<TEST_TENANT_ID>` |
| Test account | `<TEST_ACCOUNT>` |
| Evidence directory | `<EVIDENCE_DIR>` |
| Evidence JSON | `<EVIDENCE_JSON>` |
| Log query link | `<LOG_QUERY_LINK>` |
| DB export location | `<DB_EXPORT_LOCATION>` |
| Push test channel | `<PUSH_TEST_CHANNEL>` |
| Delivery id | `<DELIVERY_ID>` |
| GO/NO-GO approver | `<GO_NOGO_APPROVER>` |
| Final judgment | `<GO_OR_NO_GO>` |

## 6. GO/NO-GO Rules

GO is allowed only when all of the following are true:

- Target environment, release commit, and release artifact match the approved release boundary.
- Health/readiness checks pass and dependency status is acceptable.
- Test account login and `/api/v1/me` prove correct tenant/role.
- Market sync completes with acceptable source and data quality evidence.
- Strategy scan completes with complete result metadata and usable signal evidence where expected.
- `apply-signal` creates the expected paper trading records in the approved test tenant only.
- `evaluate-exits` returns structured results and does not corrupt paper trading state.
- Daily report push is sent only to the approved test channel.
- Delivery query proves delivery status, response code/error, retry count, and redacted payload summary.
- Logs and DB records correlate to the same request ids/task ids/scan ids/signal ids/delivery ids.
- Screenshots are archived with sensitive data masked.
- `scripts/production_evidence.py --evidence "<EVIDENCE_JSON>"` passes after the final bundle is populated.
- Rollback owner and GO/NO-GO approver explicitly approve.

NO-GO must be recorded when any critical evidence is missing, ambiguous, unverifiable, or points to failed health, auth, sync, scan, paper trading, report push, delivery, log, DB, security, or rollback readiness.

## 7. Immediate Next Step for User Approval

Before real execution, ask the user/release owner to provide or confirm:

1. `<TARGET_ENV>`, `<BASE_URL>`, and `<API_BASE_URL>`.
2. `<RELEASE_COMMIT>` and `<RELEASE_ARTIFACT>` for the exact release boundary.
3. `<TEST_TENANT_ID>`, `<TEST_ACCOUNT>`, and approved credential handoff method.
4. `<TEST_SYMBOLS>`, scan strategy/profile, and allowed market sync date range.
5. `<PUSH_TEST_CHANNEL>` and explicit approval to send one test daily report message.
6. `<LOG_SYSTEM_URL>` / `<LOG_QUERY_TEMPLATE>` and export/redaction policy.
7. `<DB_READONLY_ACCESS>` and exact allowed SQL/table scope.
8. `<EVIDENCE_DIR>`, `<EVIDENCE_JSON>`, rollback owner, and GO/NO-GO approver.
