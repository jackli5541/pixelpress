# PixelPress Backend

基于 `FastAPI + LangGraph` 的后端骨架工程，用于承载 PixelPress 的五层排版流水线。

当前阶段已完成：

- API 入口与路由分层
- `AlbumState` / `TaskState` / `BookLayout` / `UserOperation` 契约
- LangGraph 工作流骨架
- 五层能力节点占位
- 幂等、版本冲突、局部操作的基础守卫
- 内存仓储实现，便于三人并行开发各层逻辑

当前阶段未完成：

- 五层节点的真实算法实现
- 持久化数据库实现
- Redis / Worker / 队列接入
- PDF 导出、渲染服务、订单服务接入

## 目录结构

```text
backend/
  src/pixelpress_backend/
    api/
    core/
    graph/
    models/
    repositories/
    services/
    main.py
  tests/
```

## 本地运行

```bash
cd backend
uv sync --dev
uv run uvicorn --app-dir src pixelpress_backend.main:app --reload
```

## 测试

```bash
cd backend
uv run pytest
```

## 推荐工作流

```bash
cd backend
uv sync --dev
uv run pytest
uv run uvicorn --app-dir src pixelpress_backend.main:app --reload
```

说明：

- 统一使用 `uv` 管理虚拟环境和依赖。
- 不建议团队成员继续手工执行 `pip install ...` 来维护项目依赖。
- 若新增依赖，优先使用 `uv add <package>` 或 `uv add --dev <package>`。

## 节点测试说明

五层节点做单测时，通常需要上游节点已经产出的中间数据，这很正常。推荐做法不是“必须先跑完整流程”，而是：

- 通过测试夹具直接构造 `LayoutWorkflowState`
- 按需填充上游节点已经完成后的字段
- 只测试当前节点自己的输入输出和边界行为

例如：

- 测 `chapter_clustering_node` 时，直接构造带 `cleaned_photo_set` 的 `state`
- 测 `pagination_planning_node` 时，直接构造带 `chapter_plan` 的 `state`
- 测 `layout_generation_node` 时，直接构造带 `page_plan` 的 `state`
- 测 `book_scoring_node` 时，直接构造带 `page_layouts` 的 `state`

后续可统一复用 `tests/conftest.py` 里的状态工厂，减少每个人重复拼装测试输入。
