# P6b — qlib-predict CronJob 加 initContainer 从 MinIO 同步到 PVC（deploy 仓实施）
## Goal
在 `ljwx-deploy/apps/stock-etl/base/cronjob-qlib-predict-to-pg.yaml` 加入 initContainer：
- 先从 MinIO 拉取最新 `qlib_data` 与 `model artifacts` 到 PVC `/data/qlib`
- 再运行 `python -m qlib_predict.app.predict_to_pg`

## PRE-FLIGHT (MUST DO FIRST, THEN STOP)
输出 PRE-FLIGHT 并暂停，包含：

### 1) Files to add/modify
- `apps/stock-etl/base/secret-qlib-minio.yaml`
- `apps/stock-etl/base/cronjob-qlib-predict-to-pg.yaml`
- （如需）`apps/stock-etl/base/kustomization.yaml`

### 2) New env vars used by k8s
- `MINIO_ENDPOINT`
- `MINIO_ACCESS_KEY`
- `MINIO_SECRET_KEY`
- `MINIO_BUCKET`
- `MINIO_PREFIX_QDATA=qlib_data/cn`
- `MINIO_PREFIX_MODELS=artifacts/models`
- predict 容器已有：
  - `DATABASE_URL`
  - `QLIB_PROVIDER_URI=/data/qlib/qlib_data/cn`
  - `QLIB_MODEL_ROOT=/data/qlib/artifacts/models`
  - `CANDIDATE_POOL_SIZE=300`
  - `CODE_VERSION=unknown`

### 3) initContainer sync algorithm (must state clearly)
- 用 `minio/mc`：
  1) `mc alias set`
  2) 读取 `qlib_data/cn/LATEST` 得到 `BUILD_DATE`
  3) `mc mirror --overwrite --remove` 到 `/data/qlib/qlib_data/cn/`
  4) 读取 `artifacts/models/qlib_lightgbm_alpha158/LATEST` 得到 `MODEL_DATE`
  5) `mc mirror --overwrite --remove` 到模型目录
  6) 写本地 `LATEST`

### 4) Pause
等待用户 `CONFIRM P6b`

---

## Implementation requirements (after CONFIRM)
- Namespace：`ljwx-stock`
- Secret 名：`qlib-minio-secret`
- CronJob 必须包含：
  - `timeZone: Asia/Shanghai`
  - `concurrencyPolicy: Forbid`
  - `activeDeadlineSeconds: 7200`
  - PVC mount `/data/qlib`
- initContainer 失败必须让 Job 失败（不能继续跑 predict）

---

## Implementation notes (2026-03-05)
- 为避免资源尚未准备完毕时产生持续失败风暴，线上清单采用“前置检查 + 安全跳过（exit 0）”：
  - bucket 不存在时跳过；
  - `qlib_data` / model 的 `LATEST` 缺失或为空时跳过；
  - 模型文件不完整时跳过；
  - provider 目录缺失时跳过。
- `minio/mc` 镜像 tag 已固定为 `RELEASE.2025-08-13T08-35-41Z`。
