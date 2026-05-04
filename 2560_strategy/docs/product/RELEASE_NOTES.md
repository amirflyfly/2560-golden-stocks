# Release Notes

## 2026-05-04 Product hardening candidate

### Scope

- Repository hygiene now removes generated dependency directories, logs, local tool state, and build outputs from version control.
- Dashboard exposes API status, market source, data quality, mock/fallback warning, scan task count, failed task count, and candidate pool count.
- Task center supports pagination, status filtering, failure categories, cancellation, stale task detection, event history, duration, and log summaries.
- Permissions and tenant isolation are covered for unauthenticated access, unbound tenants, disabled tenants, viewer write rejection, and missing CSRF.
- Reports expose weekly/monthly summary metrics, quality buckets, and drilldown contracts.
- Backtests include execution constraints, fees/slippage, limit-up/down guard, portfolio curve, benchmark curve, excess return, risk attribution, experiment params, and parameter group comparison.
- Benchmark curves are now built from market data when no explicit benchmark return override is supplied; synthetic benchmark input remains available for controlled experiments.

### Verification

- `python -m pytest tests/test_api_v1.py -q -p no:cacheprovider`: passed, 49 tests.
- `npm test`: frontend production build passed.
- Repository hygiene check reports zero generated-file violations after cleanup.

### Release gates still requiring environment evidence

- Confirm database backup artifact for the target deployment.
- Attach staging migration reconciliation output for the target MySQL environment.
- Attach backup restore and rollback drill evidence for the target environment.
- Complete production soak before deleting remaining SQLite compatibility branches.
