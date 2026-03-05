# Codex Prompt 执行顺序与 GitOps 运维说明（对齐 ljwx-deploy / ljwx-workflow-templates）

## 0. 基线约定（重要）

`ljwx-stock` 只负责：
- 业务代码（`agent/`、`stock_etl/`、`qlib_predict/`、`qlib_bootstrap/`）
- 镜像构建与入队 workflow

部署真源在 `ljwx-deploy`：
- `apps/stock-agent/**`
- `apps/stock-etl/**`
- `release/services*.yaml`
- `release/queue.yaml`

> 结论：本仓库不再作为线上 `kubectl apply` 的入口，线上发布通过 `queue -> promoter -> ArgoCD` 完成。

---

## 1. 建议执行顺序（功能开发）

| 步骤 | Prompt | 说明 |
|------|--------|------|
| 1 | P0 | agent 骨架、DDL、FastAPI、认证限流 |
| 2 | P1 | query_kline / technical_indicators 工具 |
| 3 | P2 | 策略插件系统 + ensemble |
| 4 | P3a | 独立 qlib_predict 镜像 |
| 5 | P3b | agent 只读 reco_daily 工具 |
| 6 | P4 | LLM provider、并发执行、安全注入检测 |
| 7 | P5 | Prometheus metrics + reco QC |
| 8 | P6a | qlib bootstrap（导出、训练、发布 MinIO） |
| 9 | P6b | qlib_predict initContainer 同步 MinIO -> PVC（在 deploy 仓落地） |
| 10 | P6c | bootstrap Job/CronJob + runbook（在 deploy 仓落地） |

---

## 2. CI/CD 入口（服务仓）

本仓库的 `build-and-enqueue*` workflow 统一调用：
- `BrunoGaoSZ/ljwx-workflow-templates/.github/workflows/build-ghcr.yml@main`
- `BrunoGaoSZ/ljwx-workflow-templates/.github/workflows/enqueue-release.yml@main`

入队 service key（必须与 deploy 仓 `release/services*.yaml` 一致）：
- `ljwx-stock-agent`
- `ljwx-stock-kline-etl`
- `ljwx-stock-qlib-predict`
- `ljwx-stock-qlib-bootstrap`

默认环境：`dev`。

---

## 3. 发布链路（真实执行路径）

1. 在 `ljwx-stock` 提交代码并触发 workflow。
2. workflow 运行测试、构建 GHCR 镜像并写入 `release/queue.yaml`（目标仓：`BrunoGaoSZ/ljwx-deploy`）。
3. deploy 仓 promoter 消费 queue，更新 overlay digest：
   - `apps/stock-agent/overlays/ljwx-stock/kustomization.yaml`
   - `apps/stock-etl/overlays/ljwx-stock/kustomization.yaml`
4. ArgoCD Application 自动同步到 `ljwx-stock` namespace。

---

## 4. 变更边界（改哪里）

改 `ljwx-stock`：
- Python 业务逻辑
- Dockerfile
- CI workflow（入队参数、测试命令）
- 开发文档

改 `ljwx-deploy`：
- Deployment/CronJob/Job/Secret/ConfigMap/PVC 等 k8s 清单
- overlay 与 ArgoCD Application
- release service mapping

---

## 5. 数据库迁移（仍然手工执行）

迁移不在应用启动时自动执行，沿用脚本手工执行：

```bash
cd ljwx-stock/agent
./scripts/run_sql.sh sql/001_agent_tables.sql
./scripts/run_sql.sh sql/002_reco_qc.sql
./scripts/run_sql.sh sql/003_safety_flag.sql
```

---

## 6. 常见误区

- 误区：在本仓库执行 `kubectl apply -f k8s/...` 作为正式发布。
  - 正确：以 `ljwx-deploy` 中 Argo 管理路径为准。
- 误区：workflow `service` 名和 deploy service map 不一致。
  - 正确：必须使用已注册 key（见第 2 节）。
- 误区：只改业务仓，不改 deploy 仓 manifest。
  - 正确：运行时配置和编排改动必须同步到 deploy 仓。

---

## 7. 参考仓库

- Workflow 模板：`/root/codes/ljwx-workflow-templates`
- 部署编排真源：`/root/codes/ljwx-deploy`

---

## 8. P6 实施回写（2026-03-05）

- `P6a`：
  - dump 工具改为 vendored `qlib_dump_bin.py`，不再依赖不可用的 `qlib.scripts.dump_bin`。
  - 训练数据清洗已修复，避免 `dropna(any)` 造成训练集为空。
  - `qlib_bootstrap` 镜像已要求内置 `libgomp1`。
- `P6b`：
  - `qlib-predict` CronJob 已切到 `minio/mc:RELEASE.2025-08-13T08-35-41Z`。
  - 同步与预测流程加入前置检查，缺失依赖时安全跳过，避免重复失败告警。
- `P6c`：
  - bootstrap/predict 已在 k3s 完成链路验收，验证 `reco_daily` 可写入。
