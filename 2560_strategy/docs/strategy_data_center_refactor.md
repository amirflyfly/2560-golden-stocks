# Strategy Lifecycle And Data Center Refactor

## Current Problems

- Strategy management was not a lifecycle. The old `/strategies` API returned hard-coded defaults, while execution depended on the Python registry.
- Backtests could call external market providers repeatedly through `stock_data_service`, so the same historical K-line range was not guaranteed to be reproducible.
- Market data sync wrote daily bars locally, but the rest of the product did not consistently consume that local store first.
- Deployed strategies need timely data, but direct provider calls from strategy code make production behavior hard to audit and retry.

## Target Flow

1. Strategy draft: create or edit strategy metadata and code in the Strategy page.
2. Strategy test: run syntax validation and, for built-in registered strategies, a bounded scan sample.
3. Backtest: run strategy backtests against local data center first; external providers are cache-miss fallbacks only.
4. Deployment: mark tested strategies as deployed. Built-in strategies are runtime-registered; custom code is stored and gated until a loader/sandbox is added.
5. Production trigger: workers sync market snapshots/K-lines into MySQL, then strategy runners read local snapshots instead of calling providers directly.

## Data Policy

- Daily K-lines, volume, amount, turnover and adjust metadata are stored in `stock_daily_bars`.
- Daily K-lines are unique by `(symbol, trade_date, source, adjust)`, so `qfq`, `hfq` and `none` do not overwrite each other.
- Latest quote snapshots are stored in `stock_price_snapshots` and exposed in the Data Center page.
- Production uses MySQL through SQLAlchemy repositories.
- Development uses SQLite with the same repository contract.
- Backtest benchmark data now reads local bars first and only fetches provider data on miss, then persists fetched data back to the local store.
- `stock_data_service` now has `LocalMarketDataSource` as the first source for strategy scans and backtests.

## Mootdx Decision

The installed `mootdx` version exposes:

- `quotes(symbols)` for real-time quote snapshots.
- `bars(symbol, frequency=9)` for K-line data.
- `minute` / `minutes` for intraday time-share data.
- `transaction` / `transactions` for tick-level transactions.

This is pull-based access to Tongdaxin servers, not a durable push stream. Production should therefore use `mootdx` in a worker sync loop:

- intraday: poll quotes/minute bars for deployed strategy watchlists and persist snapshots;
- daily: sync full daily K-lines after market close;
- strategy trigger: read the latest local snapshot and write task/audit records;
- fallback: use AkShare/mock only when `mootdx` is unhealthy, and mark data quality.

Direct provider calls inside strategy logic should be treated as a development fallback, not the production path.

The current mootdx adapter treats daily `bars()` as unadjusted data. Requests for `qfq`/`hfq` intentionally fall through to an adjusted provider such as AkShare, while realtime `quotes()` remains the preferred mootdx path for intraday snapshots.

## Implemented Operational Flow

- `POST /api/v1/market-data/sync` enqueues local K-line sync. `symbols=all` resolves the provider stock list and can be capped with `max_symbols`.
- When `start_date` is omitted, market sync uses per-symbol incremental windows. Missing symbols bootstrap from `MARKET_BOOTSTRAP_DAYS` days back; already-synced symbols continue from the local latest trade date, with an optional correction window.
- `POST /api/v1/market-data/bootstrap` creates an explicit full-market bootstrap task. The production worker can queue the same startup bootstrap with `MARKET_BOOTSTRAP_ON_START=1`.
- Full-market sync is split by `batch_size` through `market.sync.plan`, which enqueues child `market.sync` tasks instead of running thousands of symbols in one task.
- `GET /api/v1/market-data/coverage` shows per-stock local K-line coverage, sources and adjust variants.
- `GET /api/v1/market-data/sync/state` shows per-symbol sync cursor state, including source, adjust, coverage start/end, last successful trade date and last error.
- `GET /api/v1/market-data/sync/runs` shows persisted sync runs. This is the long-lived audit trail; Redis/memory task state remains operational telemetry.
- `POST /api/v1/market-data/snapshots/sync` enqueues latest quote snapshot sync.
- Full-market realtime snapshots are split by `market.snapshot.plan` and child `market.snapshot` tasks.
- `GET /api/v1/market-data/snapshots` shows the latest local realtime snapshot per symbol.
- `POST /api/v1/strategies/{id}/production-run` enqueues a production strategy run with a local snapshot gate. If no realtime snapshot exists, the task completes as `blocked_no_snapshot` instead of silently calling an external provider.
- Production strategy runs also require local historical K-line data. When `local_only=true`, strategy scans are prevented from calling external providers for missing history.
- Completed production strategy runs can write paper trading signals and orders when `PAPER_TRADING_ENABLED=1`. This creates a durable chain: `trade_signals -> paper_orders -> paper_fills -> paper_positions`.
- `GET /api/v1/trading/signals`, `/api/v1/trading/paper/accounts`, `/positions`, `/orders`, `/fills` and `/summary` expose the simulated account ledger.
- `backend.infrastructure.tasks.worker` can schedule:
  - `alerts.evaluate` via `ALERT_EVALUATION_INTERVAL_SECONDS`;
  - `market.sync` via `MARKET_SYNC_INTERVAL_SECONDS`;
  - `market.snapshot` via `MARKET_SNAPSHOT_INTERVAL_SECONDS`;
  - deployed strategy production runs via `STRATEGY_RUN_INTERVAL_SECONDS`.

## Continuous Production Loop

Recommended production loop:

1. `MARKET_SYNC_SYMBOLS=all`, `MARKET_SYNC_BATCH_SIZE=200`: incrementally sync recent K-lines for the full universe into MySQL.
2. `MARKET_SNAPSHOT_SYMBOLS=all`, `MARKET_SNAPSHOT_BATCH_SIZE=500`: refresh realtime quote snapshots during market hours.
3. `STRATEGY_RUN_INTERVAL_SECONDS=300`, `STRATEGY_RUN_SCAN_LIMIT=6000`: run deployed strategies continuously against local MySQL data and the latest local snapshots.
4. Strategy logic should treat external provider calls as disabled in production runs. Missing local history blocks or reduces the run rather than silently generating mock picks.
5. Paper trading is enabled by default for production runs but remains isolated from live brokers. The reserved `BrokerAdapter` contract is present, while live order submission is disabled.

## Paper Trading MVP

The implemented simulation is intentionally conservative:

- Strategy scan output is persisted into `trade_signals` with a deterministic signal hash.
- Duplicate buys are blocked when an active position already exists for the symbol.
- Buy size uses `PAPER_CASH_PER_TRADE`, `PAPER_LOT_SIZE` and available cash.
- Market fills use the latest local `stock_price_snapshots` price.
- Exit evaluation supports stop loss, take profit and max holding days.
- Account cash, orders, fills, positions, realized PnL and unrealized PnL are persisted.
- Live trading is not active. Future broker adapters must consume the same order-intent style contract and add manual confirmation, kill switch, broker reconciliation and credential isolation.

## Remaining Hardening

- Built-in strategies still need deeper local-only rewrites where they call AkShare directly, especially `first_limit_up`.
- Custom `code_body` is syntax-tested and persisted, but not loaded into runtime until a sandboxed loader is implemented.
- Full-market production sync now has incremental cursors, but still needs trading-calendar awareness for holidays, close-ready timing,停牌/new-stock explanations and periodic qfq repair windows.
- Paper trading currently uses snapshot-price market fills. A next version should add next-trading-day open fills, A-share T+1 lots, limit-up/down checks, slippage, commission/tax details and immutable cash ledger entries.
