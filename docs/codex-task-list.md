# Codex 待完成任务清单（持续维护）

更新时间：2026-03-05 14:04 CET
来源：`codex-prompts/P0~P6c.md` + 当前代码实现扫描 + k3s 实际运行结果

## 一、实施状态总览

- 本地代码面：`P0`、`P1`、`P2`、`P3a`、`P3b`、`P4`、`P5`、`P6a` 已落地。
- 本轮用户要求的 `1~6` 已执行完成（代码、镜像、清单、集群验证均已覆盖）。
- 当前 `ljwx-stock` 命名空间下 `qlib-predict`/`qlib-bootstrap` 无 Failed Job 记录。

## 二、本轮 1~6 执行结果（2026-03-05）

1. 发布正式镜像并替换热修运行方式（完成）
   - 已构建并推送：
   - `ghcr.io/brunogao/ljwx-stock/ljwx-stock-qlib-bootstrap:20260305-fix1`
     - digest: `sha256:3179cf393e708ddc5ce3e3f62837e19f7c2c0d267cdb1bc93370edb170f72eed`
   - `ghcr.io/brunogao/ljwx-stock/ljwx-stock-qlib-predict:20260305-fix1`
     - digest: `sha256:af130411bf6cffe0e8a58ad2aab6f6f30d45d8f8521f591e49074ca7f3a14118`

2. 同步 `ljwx-deploy` 清单到正式版本（完成）
   - 已更新文件：
   - `apps/stock-etl/base/cronjob-qlib-predict-to-pg.yaml`
   - `apps/stock-etl/base/cronjob-qlib-bootstrap-weekly.yaml`
   - `apps/stock-etl/base/job-qlib-bootstrap.yaml`
   - `apps/stock-etl/overlays/ljwx-stock/kustomization.yaml`
   - 已将 qlib predict 的“前置检查+安全跳过”逻辑固化进 base 清单。

3. 清理历史临时资源（完成）
   - 已删除失败/临时 hotfix Job：
   - `qlib-bootstrap-hotfix-1772707315`
   - `qlib-bootstrap-hotfix-1772707667`
   - `qlib-bootstrap-hotfix-1772708435`
   - `qlib-bootstrap-hotfix-1772713137`
   - `qlib-predict-hotfix-1772714072`
   - 已删除临时 ConfigMap：
   - `qlib-bootstrap-hotfix-files`
   - `qlib-predict-hotfix-files`

4. 统一测试入口（完成）
   - 新增：`scripts/ci/run_module_tests.sh`
   - 按模块分别执行：`agent` / `qlib_bootstrap` / `qlib_predict`，避免根目录同名测试模块冲突。

5. 处理 `pytest-asyncio` deprecation warning（完成）
   - 新增：
   - `qlib_bootstrap/pytest.ini`
   - `qlib_predict/pytest.ini`
   - 显式设置：`asyncio_default_fixture_loop_scope = function`。

6. 回写 codex-prompts 文档差异（完成）
   - 已更新：
   - `codex-prompts/EXECUTION.md`
   - `codex-prompts/P6a.md`
   - `codex-prompts/P6b.md`
   - `codex-prompts/P6c.md`

## 三、本轮新增验证证据

1. 代码质量与测试
   - `uv run ruff check .` -> `All checks passed!`
   - `uv run ruff format --check .` -> `90 files already formatted`
   - `bash scripts/ci/run_module_tests.sh` -> `43 passed, 1 skipped` + `2 passed` + `12 passed`

2. 正式镜像实跑（无 hotfix 注入）
   - bootstrap：`job/qlib-bootstrap-formal-verify-1772715643` `Complete`，日志 `status=ok`
   - predict：`job/qlib-predict-formal-verify-1772715535` `Complete`，日志 `written_count=300`

3. 写库核验
   - `market.reco_daily` 在 `trade_date=2026-03-05`、`strategy_name=qlib_lightgbm_v1` 下：
   - `row_count=300`
   - `code_version=p3a-fix20260305`

## 四、当前剩余待办（非本轮 1~6）

1. 将 `ljwx-deploy` 相关变更合入 ArgoCD 实际跟踪分支（通常为 `main`），避免被自动回滚。
2. 补充一份 deploy 侧 evidence 记录文件（`evidence/records/*.yaml`）归档本轮正式镜像 digest 与验证日志。

## 五、维护规则

- 每次 Codex 完成任务后，必须更新本文件：状态、时间、证据。
- 新任务统一写入“当前剩余待办”，并标注优先级（P0/P1/P2）。
