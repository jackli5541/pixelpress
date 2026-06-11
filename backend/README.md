# PixelPress Backend

基于 `FastAPI + LangGraph` 的后端骨架工程，用于承载 PixelPress 的五层排版流水线。

当前阶段已完成：

- API 入口与路由分层
- `AlbumState` / `TaskState` / `BookLayout` / `UserOperation` 契约
- LangGraph 工作流骨架
- 五层能力节点占位
- 幂等、版本冲突、局部操作的基础守卫
- 内存仓储实现，便于三人并行开发各层逻辑
- 五层核心节点的输入输出 Pydantic 契约模型
- `LayoutWorkflowState` 强类型化，统一承载节点间中间产物
- 节点内显式输入校验与结构化输出组装
- 工作流契约测试，覆盖节点输出和必填字段校验

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

## 本次更新记录

本次实现聚焦于“每个核心 node 是否需要建立 Pydantic 输入输出模型”的落地，已完成以下内容：

- 新增 `src/pixelpress_backend/models/workflow_contracts.py`
  - 定义五层流水线的核心中间产物契约：
    - `CleanedPhotoSet`
    - `ChapterPlan`
    - `PagePlan`
    - `LayoutDraft`
    - `ScoreSnapshot`
  - 定义对应节点的 `Input / Output` 模型：
    - `PhotoCleaningInput / Output`
    - `ChapterClusteringInput / Output`
    - `PaginationPlanningInput / Output`
    - `LayoutGenerationInput / Output`
    - `BookScoringInput / Output`
- 新增 `src/pixelpress_backend/models/workflow_state.py`
  - 将 `LayoutWorkflowState` 从松散 `dict` 字段改为强类型字段
  - 将 `cleaned_photo_set / chapter_plan / page_plan / page_layouts / score_snapshot / decision` 收紧为模型或枚举
- 更新核心 graph 节点
  - `photo_cleaning_node.py`：直接写入强类型 `CleanedPhotoSet`
  - `chapter_clustering_node.py`：显式消费 `CleanedPhotoSet`，产出强类型 `ChapterPlan`
  - `pagination_planning_node.py`：显式消费 `ChapterPlan`，产出强类型 `PagePlan`
  - `layout_generation_node.py`：显式消费 `PagePlan`，产出强类型 `LayoutDraft`
  - `book_scoring_node.py`：显式校验 `ChapterPlan / PagePlan / LayoutDraft`，产出强类型 `ScoreSnapshot` 和枚举型 `decision`
  - `finalize_node.py`：`finalize_node` 直接消费强类型状态字段组装最终 `BookLayout`
  - `routing.py`：集中承载 `score_router` 等工作流路由函数
- 新增测试 `tests/graph/test_workflow_contracts.py`
  - 校验节点输出是否符合契约
  - 校验强类型状态在缺少必填字段时是否会提前抛出校验错误
  - 校验评分节点输出是否符合 `ScoreSnapshot` 结构
- 验证结果
  - `pytest` 通过，当前为 `9 passed`

## README 更新约定

后续每次有实质性改动时，都在本 README 追加一条“更新记录”。建议使用下面格式：

```md
## 更新记录 - YYYY-MM-DD

- 目标
  - 这次改动要解决什么问题
- 修改内容
  - 新增了哪些文件
  - 更新了哪些文件
  - 各文件分别做了什么
- 契约影响
  - 修改了哪些领域模型 / DTO / 状态机
  - 是否影响 `BookLayout.version`
  - 是否影响幂等、缓存、导出一致性
- 验证
  - 跑了哪些测试
  - 结果是否通过
- 待办
  - 下一步准备继续补什么
```

推荐要求：

- 不只写“改了什么”，还要写“为什么改”
- 至少列出新增文件和被修改文件
- 若改动涉及状态机、版本、幂等键、导出参数，必须单独写明
- 若只完成骨架，也要明确标注“真实业务逻辑尚未实现”
