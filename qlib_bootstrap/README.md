# qlib_bootstrap

离线 Bootstrap 镜像：从 PostgreSQL 的 `market.kline_daily` 导出 qfq 日线，生成 Qlib provider 数据，训练 LightGBM，并发布到 MinIO。

## 生产部署（GitOps）

- Bootstrap 的 Job/CronJob 与 MinIO Secret 在 `ljwx-deploy/apps/stock-etl/**` 维护
- 本仓只负责训练/发布逻辑与镜像构建
- 详见 [`docs/gitops-deployment.md`](../docs/gitops-deployment.md)

## 环境变量

- `DATABASE_URL`（必填）
- `MINIO_ENDPOINT`（默认：`http://minio.infra.svc.cluster.local:9000`）
- `MINIO_BUCKET`（默认：`ljwx-qlib`）
- `MINIO_ACCESS_KEY`（必填）
- `MINIO_SECRET_KEY`（必填）
- `QLIB_REGION`（默认：`cn`）
- `OUTPUT_ROOT`（默认：`/work/out`）
- `MODEL_NAME`（默认：`qlib_lightgbm_alpha158`）
- `HORIZON_DAYS`（默认：`5`）
- `TRAIN_END_DATE`（可选，默认取数据库最新交易日）
- `LOOKBACK_YEARS`（默认：`8`）
- `EXPORT_LOOKBACK_CALENDAR_DAYS`（默认：`4500`）
- `CODE_VERSION`（默认：`unknown`）
- `DRY_RUN`（默认：`0`）

## 运行

仅预检（推荐先执行）：

```bash
python -m qlib_bootstrap.app.main --preflight-only
```

完整执行：

```bash
python -m qlib_bootstrap.app.main
```

仅做计划检查（不执行导出/训练/发布）：

```bash
DRY_RUN=1 python -m qlib_bootstrap.app.main
```

## 退出码

- `0`: 成功
- `2`: preflight 失败
- `3`: 发布到 MinIO 失败
- `1`: 其他失败

## MinIO 发布路径

- `s3://<bucket>/qlib_data/cn/<BUILD_DATE>/...`
- `s3://<bucket>/qlib_data/cn/LATEST`
- `s3://<bucket>/artifacts/models/<MODEL_NAME>/<MODEL_DATE>/...`
- `s3://<bucket>/artifacts/models/<MODEL_NAME>/LATEST`

`LATEST` 采用“先写 tmp 再覆盖”更新。
