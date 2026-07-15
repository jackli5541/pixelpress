# AGENTS.md

给 Codex 的仓库内规则。只写做事前必须知道的点。

## 先这样工作

- 优先用 `start.bat` 管理容器，不要自己重拼一套启动命令。它统一处理 `compose.prod.yml`、`compose.test.yml` 和运行时环境变量。
- 后端改动默认落在 `modules -> services -> repositories` 这条链上；不要把业务逻辑直接塞回 `api.py`。
- 核心流程按阶段拆分，保持 API、Service、Engine、Repository、Storage 职责边界；不要继续堆大文件、大 Service 或大页面。
- 算法优化优先限制在 Engine 内部，并保持接口字段、任务状态和前端流程契约稳定；契约变化必须同步前后端类型、适配逻辑和测试。
- 异步任务看 `backend/app/jobs/handlers.py`，真实队列是 ARQ；不要按 README 里的旧 Celery 说法继续扩展。
- 涉及照片、预览图、导出文件时，统一走 `backend/app/storage/file_store.py` 的存储抽象，不要写死本地文件路径。
- 改相册流程时，同时检查 `frontend/src/shared/workflow/albumWorkflow.ts`。前端默认流程顺序是 `upload -> cleaning -> chapters -> planning -> export`。
- 改接口时保持前端约定不变：`frontend/src/shared/api/http.ts` 期待统一响应包 `{ code, message, request_id, data }`。
- 改登录态或权限时，同时看 `frontend/src/shared/auth.ts` 和 `frontend/src/app/router/index.ts`，因为路由守卫依赖 token 和 `meta.requiresAuth / requiresRole`。
- 生产相关配置不能破坏 `AUTH_SECRET_KEY` / `SECRETS_MASTER_KEY` 校验；规则在 `backend/app/core/config.py`。

## 改完至少这样验

- 后端接口、任务流、数据库、权限：`start.bat test`
- 渲染 / 预览 / 导出链路：`start.bat test-render`
- Docker / 启动脚本 / 环境变量：`start.bat ps`，必要时再跑 `start.bat`
- 前端页面、路由、鉴权、类型：`cd frontend && npm run build`
- 只改文档：检查 diff 即可，不强行跑整套测试

## 更新规则

- 不复制 README，不写背景介绍。
- 只补充“以后做事还会反复用到的规则、坑点、验收命令”。
- 发现这里过时，就在同次改动里顺手更新。
