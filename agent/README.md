# ljwx-stock agent

`agent` 子模块提供“自然语言驱动的股票信号系统”骨架服务，基于 FastAPI + asyncpg + Pydantic v2。

## 目录

- `app/`: 服务源码
- `sql/`: DDL
- `scripts/`: 运维脚本
- `tests/`: 单元测试
- `k8s/`: Kubernetes 清单

## 环境变量

- `DATABASE_URL` (required)
- `API_KEY` (required)
- `RATE_LIMIT_RPM` (default: `30`)
- `MAX_TOKENS_PER_RUN` (default: `50000`)
- `LOG_LEVEL` (default: `INFO`)
- `ENVIRONMENT` (default: `development`)
- `DB_POOL_MIN_SIZE` (default: `1`)
- `DB_POOL_MAX_SIZE` (default: `10`)
- `KLINE_QUERY_TIMEOUT_SECONDS` (default: `5`)
- `KLINE_DEFAULT_LIMIT` (default: `60`)
- `KLINE_MAX_LIMIT` (default: `500`)
- `KLINE_BULK_PER_SYMBOL_LIMIT` (default: `60`)
- `KLINE_BULK_MAX_SYMBOLS` (default: `500`)
- `KLINE_BULK_MAX_ROWS` (default: `20000`)
- `CANDIDATE_POOL_SIZE` (default: `300`)
- `DISPLAY_TOP_N` (default: `20`, max `50`)
- `MIN_AMOUNT_AVG` (default: `10000000`)
- `LOOKBACK_DAYS_CALENDAR` (default: `150`)
- `WRITE_RECO` (default: `true`)
- `CODE_VERSION` (default: `unknown`)
- `LLM_PROVIDER` (default: `claude`, optional: `mock`)
- `ANTHROPIC_AUTH_TOKEN` (`LLM_PROVIDER=claude` 时必填)
- `ANTHROPIC_BASE_URL` (default: `https://api.anthropic.com`)
- `ANTHROPIC_MODEL` (default: `claude-sonnet-4-6-20260217`)
- `MAX_USER_QUERY_LEN` (default: `2000`)
- `METRICS_ENABLED` (default: `true`)
- `QC_ENABLED` (default: `true`)
- `QC_LOOKBACK_DAYS` (default: `20`)
- `QC_COLD_START_MIN` (default: `5`)
- `QC_OVERLAP_ERROR_THRESHOLD` (default: `1.0`)
- `QC_OVERLAP_WARN_THRESHOLD` (default: `0.9`)

## 安装依赖

```bash
cd agent
uv pip install -r requirements.txt
```

## 手工执行 Migration（必须手工，禁止应用启动自动迁移）

```bash
cd agent
export DATABASE_URL='postgresql://user:pass@host:5432/dbname'
./scripts/run_sql.sh sql/001_agent_tables.sql
./scripts/run_sql.sh sql/002_reco_qc.sql
./scripts/run_sql.sh sql/003_safety_flag.sql
```

说明：应用启动流程不会自动执行 SQL migration，避免多 Pod 竞争。

## 启动服务

```bash
cd agent
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## API

- `GET /v1/health`
- `GET /metrics`
- `POST /v1/chat`
- `POST /v1/qc/run`
  - Header: `X-API-Key`
  - Body:
    ```json
    {
      "user_query": "请分析某股票走势并给出推荐",
      "session_id": "optional-session"
    }
    ```

## Built-in Tools

- `query_kline`: 单标的 K 线查询（按 `symbol + adjust + 日期范围` 过滤）
- `query_kline_bulk`: 多标的/全市场批量查询（包含按 symbol 截断与总量保护）
- `technical_indicators`: 基于 `query_kline` 的 MA/RSI 计算
- `strategy_ensemble_v1`: 两策略融合选股（强制 bulk + qfq，写入 `market.reco_daily`）

## 测试

```bash
pytest -q
```
