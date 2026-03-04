# stock_etl

A-share daily kline ETL for `market.kline_daily`.

## Modes
- `backfill`: backfill recent N trading days (default 1200)
- `daily`: refresh recent calendar window (default 7 days)
- `reconcile`: quarterly full-range reconcile for previous quarter

## Required env
- `DATABASE_URL`

## Key env
- `RUN_MODE` (`backfill|daily|reconcile`)
- `ADJUST` (default `qfq`)
- `TRADING_DAYS` (default `1200`)
- `DAILY_LOOKBACK_CALENDAR_DAYS` (default `7`)
- `RECONCILE_LOOKBACK_CALENDAR_DAYS` (default `100`)
- `SYMBOL_LIMIT` (`0` means all symbols)
- `BATCH_SIZE` (default `2000`)
- `REQUEST_SLEEP_MS` (default `30`)
- `REQUEST_RETRIES` (default `2`)

## Local run
```bash
export DATABASE_URL='postgresql://postgres:***@postgres-lb.infra.svc.cluster.local:5432/ljwx_stock'
export RUN_MODE=backfill
python -m stock_etl.app.main
```
