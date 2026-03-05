# P6a — qlib-bootstrap（Postgres→QlibData→Train→Publish→MinIO）
## Goal
新增独立子目录 `qlib_bootstrap/`（独立镜像），实现：
1) **Preflight**：检查 `market.kline_daily` 是否存在且有 `adjust='qfq'` 数据  
2) **Export Qlib Data**：从 Postgres 导出 raw（CSV）并用 Qlib dump 工具生成 `qlib_data/cn`  
3) **Train**：周更训练 LightGBM（或你们既定模型），产出 `model.pkl + handler_config.yaml + meta.json`  
4) **Publish**：上传 MinIO，原子更新 `LATEST`

### Contract
- 不改现有 `stock-etl/` 与 `agent/` 代码
- 只依赖 Postgres 事实表 `market.kline_daily`（如果不存在，preflight 必须清晰失败）
- MinIO 作为唯一真源：`s3://ljwx-qlib/...`
- PVC 只是运行时 cache（P6b 处理）

---

## PRE-FLIGHT (MUST DO FIRST, THEN STOP)
在输出任何代码前，先输出一个 `PRE-FLIGHT` 块，包含：

### 1) Files to add (exact paths)
必须列出将新增的全部文件（repo-relative），至少包括：
- `qlib_bootstrap/README.md`
- `qlib_bootstrap/requirements.txt`
- `qlib_bootstrap/Dockerfile`
- `qlib_bootstrap/app/__init__.py`
- `qlib_bootstrap/app/config.py`
- `qlib_bootstrap/app/preflight.py`
- `qlib_bootstrap/app/export_raw_csv.py`
- `qlib_bootstrap/app/dump_qlib_data.py`
- `qlib_bootstrap/app/train_model.py`
- `qlib_bootstrap/app/publish_minio.py`
- `qlib_bootstrap/app/main.py`
- `qlib_bootstrap/tests/test_params_hash.py`
- `qlib_bootstrap/tests/test_minio_latest_atomic.py`

### 2) Existing interfaces depended on (none)
声明：该模块独立，不导入 agent/etl 代码。仅依赖 PostgreSQL 与 MinIO API。

### 3) New interface signatures
列出关键函数签名（必须精确到参数/返回）：
- `get_settings() -> Settings`
- `preflight_or_raise(pg_dsn: str) -> dict`
- `export_raw_csv(pg_dsn: str, out_dir: str, start_date: str, end_date: str) -> dict`
- `dump_qlib_data(raw_dir: str, qlib_out_dir: str, region: str) -> dict`
- `train_lightgbm(qlib_provider_uri: str, out_model_dir: str, end_date: str, horizon: int) -> dict`
- `publish_to_minio(local_dir: str, minio_endpoint: str, bucket: str, prefix: str) -> dict`
- `atomic_write_latest(minio..., latest_key: str, value: str) -> None`

### 4) Environment variables (defaults)
必须列出并在代码中实现：
- `DATABASE_URL`（required）例如 `postgresql://postgres:...@postgres-lb.infra.svc.cluster.local:5432/ljwx_stock`
- `MINIO_ENDPOINT=http://minio.infra.svc.cluster.local:9000`
- `MINIO_BUCKET=ljwx-qlib`
- `MINIO_ACCESS_KEY`（required）
- `MINIO_SECRET_KEY`（required）
- `QLIB_REGION=cn`
- `OUTPUT_ROOT=/work/out`
- `MODEL_NAME=qlib_lightgbm_alpha158`
- `HORIZON_DAYS=5`
- `TRAIN_END_DATE`（optional；默认用 Postgres 最新交易日）
- `LOOKBACK_YEARS=8`（训练窗口）
- `EXPORT_LOOKBACK_CALENDAR_DAYS=4500`（用于导出足够历史，默认约 18 年；可后续调小）
- `DRY_RUN=0`

### 5) Tests & assertions
列出测试文件与断言：
- `test_params_hash.py`：稳定 16 位 hash（`sha256(json.dumps(params, sort_keys=True, separators=(',', ':')))` 前 16）
- `test_minio_latest_atomic.py`：`LATEST` 更新必须“先写 tmp 再覆盖”，确保不会出现空/半写状态（用 stub/mock 验证调用顺序）

### 6) Pause
PRE-FLIGHT 输出后必须停止并等待用户回复 `CONFIRM P6a`。

---

## Implementation requirements (after CONFIRM)
### A) Preflight behavior (hard requirement)
连接 `DATABASE_URL` 后：
1) 若 schema `market` 不存在或表 `market.kline_daily` 不存在：抛 `RuntimeError`，消息包含：
   - “market.kline_daily not found”
   - “run ETL migration / ingest first”
2) 若存在但 `adjust='qfq'` 行数为 0：抛 `RuntimeError`，消息包含 “no qfq data”
3) 输出 summary：min/max trade_date，行数，symbol 数

### B) Export raw CSV format
- 从 `market.kline_daily` 拉取列：`trade_date, symbol, open, high, low, close, volume, amount`
- 仅使用 `adjust='qfq'`
- 输出 raw csv 到：`{OUTPUT_ROOT}/raw/`，每个 symbol 一个文件，例如：
  - `raw/features/SH600000.csv`（或 `SZ000001.csv`），列名固定：
    `date,open,high,low,close,volume,amount`
- Symbol 映射：
  - `6xxxxx -> SHxxxxxx`
  - 其他 -> `SZxxxxxx`

### C) Dump qlib_data
- 调用 Qlib 官方 dump 工具（用 subprocess 或其 Python API），将 raw csv 转成：
  - `{OUTPUT_ROOT}/qlib_data/cn/`（最终 provider 目录）
- 同时生成 `calendar` 与 `instruments`（全市场 instruments）

### D) Train model artifacts directory convention
训练输出本地目录：
- `{OUTPUT_ROOT}/artifacts/models/{MODEL_NAME}/{YYYYMMDD}/`
  - `model.pkl`
  - `handler_config.yaml`
  - `meta.json`（必须含：model_version, data_cutoff, code_version, params_hash, horizon_days, provider_uri）

并生成本地：
- `{OUTPUT_ROOT}/artifacts/models/{MODEL_NAME}/LATEST`（内容 YYYYMMDD）

### E) Publish to MinIO (truth source)
上传到 bucket `ljwx-qlib`：
- `qlib_data/cn/{BUILD_DATE}/...`（整个 cn provider 目录内容）
- `qlib_data/cn/LATEST`（内容 BUILD_DATE）
- `artifacts/models/{MODEL_NAME}/{YYYYMMDD}/...`
- `artifacts/models/{MODEL_NAME}/LATEST`

`LATEST` 更新必须原子：
- 先写 `.../LATEST.tmp` 再覆盖 `.../LATEST`

### F) Exit codes
- Preflight fail: exit 2
- Publish fail: exit 3
- Success: exit 0

---

## Implementation notes (2026-03-05)
- `pyqlib==0.9.7` 镜像内不可用 `qlib.scripts.dump_bin` 模块，实际实现改为 vendored 脚本：
  - `qlib_bootstrap/app/vendor/qlib_dump_bin.py`
  - `qlib_bootstrap/app/dump_qlib_data.py` 通过 subprocess 调用该脚本。
- 训练特征清洗从 `dropna(any)` 调整为：
  - 仅剔除 label 缺失；
  - `inf/-inf -> NaN`；
  - 特征中位数 + `0` 填充；
  - 解决训练集被清空问题。
- LightGBM 运行依赖 `libgomp.so.1`，正式 Dockerfile 已加入 `libgomp1`，避免运行时临时安装。
