# qlib_predict

离线 Qlib 推理镜像，读取 PVC 上的 `qlib_data/artifacts` 并写入 `market.reco_daily`。

## 生产部署（GitOps）

- 运行时 CronJob/Secret/PVC 清单真源在 `ljwx-deploy/apps/stock-etl/**`
- 本仓负责代码与镜像构建，部署由 `release queue -> promoter -> ArgoCD` 推进
- 详见 [`docs/gitops-deployment.md`](../docs/gitops-deployment.md)

## 目录约定

- `QLIB_PROVIDER_URI` 默认 `/data/qlib/qlib_data/cn`
- `QLIB_MODEL_ROOT` 默认 `/data/qlib/artifacts/models`
- 模型目录固定：`{QLIB_MODEL_ROOT}/qlib_lightgbm_alpha158/`
  - `LATEST`（内容为 `YYYYMMDD`）
  - `{YYYYMMDD}/model.pkl`
  - `{YYYYMMDD}/handler_config.yaml`
  - `{YYYYMMDD}/meta.json`

示例：

```text
/data/qlib/artifacts/models/
  qlib_lightgbm_alpha158/
    LATEST
    20260301/
      model.pkl
      handler_config.yaml
      meta.json
```

`LATEST` 文件内容示例：

```text
20260301
```

## 环境变量

- `DATABASE_URL`（required）
- `QLIB_PROVIDER_URI`（优先，default: unset）
- `QLIB_MODEL_ROOT`（优先，default: unset）
- `QLIB_DATA_DIR`（兼容 P3a，default: `/data/qlib/data`；当 `QLIB_PROVIDER_URI` 为空时使用）
- `MODEL_DIR`（兼容 P3a，default: `/data/qlib/models`；当 `QLIB_MODEL_ROOT` 为空时使用）
- `QLIB_MODEL_DATE`（optional，覆盖 `LATEST`）
- `PREDICT_DATE`（optional，默认最近交易日）
- `PREDICT_TRADE_DATE`（兼容 P3a，`PREDICT_DATE` 为空时生效）
- `CANDIDATE_POOL_SIZE`（default: `300`）
- `CODE_VERSION`（default: `unknown`）

## 构建与推送

```bash
docker build -t ghcr.io/brunogao/ljwx-stock-qlib-predict:latest qlib_predict
docker push ghcr.io/brunogao/ljwx-stock-qlib-predict:latest
```

## 运行

```bash
cd /path/to/repo-root
export DATABASE_URL='postgresql://user:pass@host:5432/db'
python -m qlib_predict.app.predict_to_pg
```

仅做路径检查（dry-run）：

```bash
python -m qlib_predict.app.predict_to_pg --dry-run
```

## Migration 说明

`qlib_predict` 不会在启动时自动执行 migration。`reco_daily` 表结构需通过外部脚本或手工 SQL 维护。

## PVC 挂载要求

运行容器时需要把 PVC 挂载到 `/data/qlib`，确保以下路径可读：

- `/data/qlib/qlib_data/cn`
- `/data/qlib/artifacts/models/qlib_lightgbm_alpha158`
