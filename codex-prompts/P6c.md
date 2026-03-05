# P6c — qlib-bootstrap Job/CronJob + Secret（MinIO）+ 最小 Runbook（deploy 仓实施）
## Goal
在 `ljwx-deploy` 提供：
1) `qlib-minio-secret`（或复用现有 secret）
2) `Job` 手动触发 bootstrap
3) `CronJob` 周更 bootstrap
4) runbook：执行顺序、观测、回滚（切 LATEST）

## PRE-FLIGHT (MUST DO FIRST, THEN STOP)
输出 PRE-FLIGHT 并暂停，包含：

### 1) Files to add
- `apps/stock-etl/base/job-qlib-bootstrap.yaml`
- `apps/stock-etl/base/cronjob-qlib-bootstrap-weekly.yaml`
- `docs/qlib_bootstrap_runbook.md`（在 deploy 仓）

### 2) Schedules & constraints
- Cron schedule：每周六 03:00 Asia/Shanghai
- `concurrencyPolicy: Forbid`
- `activeDeadlineSeconds: 21600`（6h）
- 资源建议：requests `cpu 1, mem 2Gi`，limits `cpu 2, mem 6Gi`

### 3) Acceptance criteria (must list)
- 若 `market.kline_daily` 缺失：Job 失败且日志包含 `market.kline_daily not found`
- 若成功：MinIO 中 `LATEST` 存在且指向有效目录；`model.pkl` 可下载；预测 CronJob 可跑通并写入 `reco_daily`

### 4) Pause
等待 `CONFIRM P6c`

---

## Implementation notes (2026-03-05)
- bootstrap 已在 k3s 完成实跑，成功发布：
  - `qlib_data/cn/20260305`
  - `artifacts/models/qlib_lightgbm_alpha158/20260305`
- 相关运行镜像需内置 `libgomp1`，否则 LightGBM 在训练/推理阶段会报 `libgomp.so.1` 缺失。
- 当前接受标准新增一条：`qlib-predict` 必须可在同日写入 `market.reco_daily`，并验证 `row_count > 0`。
