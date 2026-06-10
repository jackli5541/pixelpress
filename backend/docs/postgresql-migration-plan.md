# PostgreSQL 迁移方案设计

> 状态：待确认 | 关联：AI自动排版系统设计方案-v2.md 第 8 节

## 1. 目标

将当前 `MemoryStore`（内存存储）替换为 PostgreSQL，实现数据持久化，支持进程重启后数据不丢失。

## 2. 当前状态分析

### 2.1 内存存储结构（`repositories/memory.py`）

| 字段 | 类型 | 键 | 值 |
|------|------|-----|-----|
| `albums` | `dict[str, AlbumState]` | `album_id` | 相册状态 |
| `tasks` | `dict[str, TaskState]` | `task_id` | 任务状态 |
| `layouts` | `dict[str, dict[int, BookLayout]]` | `album_id` → `version` | 布局版本 |
| `operations` | `dict[str, UserOperation]` | `operation_id` | 用户操作记录 |
| `idempotency_map` | `dict[str, str]` | `album_id:idempotency_key` | 幂等键 → task_id |

### 2.2 数据访问方

| 文件 | 访问次数 | 操作类型 |
|------|----------|----------|
| `services/layout_service.py` | 14 处 | album CRUD、task CRUD、layout CRUD、幂等检查、复杂查询 |
| `services/operation_service.py` | 2 处 | operation 插入、task 插入 |
| `tests/conftest.py` | 5 处 | 测试清理（`store.clear()`） |
| `tests/test_app.py` | 5 处 | 测试清理 |

### 2.3 唯一复杂查询

`layout_service.py` 第 48-54 行，查询同一相册下正在运行的全书级生成任务：

```python
running_full_tasks = [
    item for item in store.tasks.values()
    if item.album_id == request.album_id
    and item.task_type == TaskType.LAYOUT_GENERATE
    and item.status in {TaskStatus.QUEUED, TaskStatus.RUNNING}
]
```

迁移后需通过联合索引 `(album_id, task_type, status)` 加速此查询。

---

## 3. 数据库表设计

### 3.1 ER 图

```
┌──────────┐     ┌──────────────┐     ┌──────────────────┐
│  albums  │────→│  task_runs   │←────│ idempotency_keys │
│  (PK)    │     │  (FK album)  │     │  (FK task)       │
└──────────┘     └──────────────┘     └──────────────────┘
     │
     ├──→ book_layouts (联合 PK: album_id + version)
     │
     └──→ user_operations (FK album)
```

### 3.2 建表语句

#### albums

```sql
CREATE TABLE albums (
    album_id                VARCHAR(64) PRIMARY KEY,
    status                  VARCHAR(20) NOT NULL DEFAULT 'draft',
    current_layout_version  INTEGER,
    latest_completed_task_id VARCHAR(64),
    allow_preview           BOOLEAN NOT NULL DEFAULT FALSE,
    allow_export            BOOLEAN NOT NULL DEFAULT FALSE,
    allow_order             BOOLEAN NOT NULL DEFAULT FALSE,
    feature_status          VARCHAR(20) NOT NULL DEFAULT 'pending',
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

- `status`：对应 `AlbumStatus` 枚举（draft / generating / reviewable / locked / ordered / archived）
- `feature_status`：对应 `FeatureStatus` 枚举（pending / extracting / partial / ready / failed）
- `current_layout_version` 和 `latest_completed_task_id`：冗余存储，加速查询，实际数据分别在 `book_layouts` 和 `task_runs` 表中

#### task_runs

```sql
CREATE TABLE task_runs (
    task_id             VARCHAR(64) PRIMARY KEY,
    album_id            VARCHAR(64) NOT NULL REFERENCES albums(album_id),
    task_type           VARCHAR(30) NOT NULL,
    status              VARCHAR(20) NOT NULL DEFAULT 'queued',
    idempotency_key     VARCHAR(128) NOT NULL,
    base_version        INTEGER,
    result_version      INTEGER,
    error_code          VARCHAR(50),
    degrade_reasons     JSONB DEFAULT '[]',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE(idempotency_key)
);

CREATE INDEX idx_task_album_type_status ON task_runs(album_id, task_type, status);
```

- `task_type`：对应 `TaskType` 枚举（feature_extract / layout_generate / partial_regenerate / render_preview / export_pdf）
- `status`：对应 `TaskStatus` 枚举（queued / running / completed / failed / cancelled / timed_out / partial）
- `degrade_reasons`：用 JSONB 存储 `string[]`，如 `["render_pending", "score_skipped"]`
- `UNIQUE(idempotency_key)`：幂等键全局唯一，防止重复提交
- 联合索引 `idx_task_album_type_status`：优化"查同相册运行中任务"查询

#### book_layouts

```sql
CREATE TABLE book_layouts (
    album_id            VARCHAR(64) NOT NULL REFERENCES albums(album_id),
    version             INTEGER NOT NULL,
    status              VARCHAR(20) NOT NULL DEFAULT 'draft',
    base_version        INTEGER,
    is_partial          BOOLEAN NOT NULL DEFAULT FALSE,
    pages               JSONB DEFAULT '[]',
    chapters            JSONB DEFAULT '[]',
    score_snapshot      JSONB DEFAULT '{}',
    generation_meta     JSONB DEFAULT '{}',
    render_snapshot     JSONB DEFAULT '{}',
    export_snapshot     JSONB DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (album_id, version)
);
```

- `status`：对应 `BookLayoutStatus` 枚举（draft / locked / exported）
- `pages`、`chapters`、`score_snapshot` 等嵌套结构用 JSONB 存储，与 Pydantic 模型中的 `JSONDict` 类型保持一致，无需拆表
- 联合主键 `(album_id, version)` 天然支持"同一相册多版本"的查询模式

#### user_operations

```sql
CREATE TABLE user_operations (
    operation_id    VARCHAR(64) PRIMARY KEY,
    album_id        VARCHAR(64) NOT NULL REFERENCES albums(album_id),
    base_version    INTEGER NOT NULL,
    op_type         VARCHAR(30) NOT NULL,
    payload         JSONB DEFAULT '{}',
    actor_type      VARCHAR(10) NOT NULL,
    actor_id        VARCHAR(64) NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_op_album ON user_operations(album_id);
```

- `op_type`：对应 `OperationType` 枚举（13 种操作类型）
- `actor` 拆为 `actor_type`（user / system / agent）和 `actor_id` 两个字段，便于查询
- `payload` 用 JSONB 存储操作参数

#### idempotency_keys

```sql
CREATE TABLE idempotency_keys (
    scope       VARCHAR(200) PRIMARY KEY,
    task_id     VARCHAR(64) NOT NULL REFERENCES task_runs(task_id),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

- `scope`：格式为 `{album_id}:{idempotency_key}`，用于快速检索幂等请求
- 独立成表而非放在 `task_runs` 中，便于后续 TTL 过期清理

---

## 4. 代码架构

### 4.1 新增文件结构

```
backend/src/pixelpress_backend/
├── db/                              # 新建：数据库模块
│   ├── __init__.py
│   ├── engine.py                    # SQLAlchemy 引擎 + 会话工厂
│   ├── base.py                      # Base = declarative_base()
│   └── models.py                    # 5 个 SQLAlchemy ORM 模型
├── repositories/
│   ├── __init__.py
│   ├── memory.py                    # 保留不变（测试用）
│   └── postgres.py                  # 新建：PostgreSQL 仓库实现
├── migrations/                      # 新建：Alembic 迁移目录
│   ├── env.py
│   ├── versions/
│   │   └── 0001_initial_schema.py   # 初始表结构
│   └── alembic.ini
```

### 4.2 ORM 模型设计（`db/models.py`）

5 个 SQLAlchemy 模型，与 Pydantic 领域模型字段一一对应。每个模型提供两个转换方法：

```python
class AlbumModel(Base):
    __tablename__ = "albums"
    album_id = Column(String(64), primary_key=True)
    # ... 其余字段

    @classmethod
    def from_domain(cls, album: AlbumState) -> "AlbumModel":
        """Pydantic → ORM"""
        ...

    def to_domain(self) -> AlbumState:
        """ORM → Pydantic"""
        ...
```

转换方法的作用：服务层继续使用 Pydantic 模型（类型安全），仓库层负责 ORM ↔ Pydantic 转换。

### 4.3 仓库层设计（`repositories/postgres.py`）

实现与 `MemoryStore` 相同的接口，内部使用 SQLAlchemy 会话：

| 方法 | SQL 操作 | 调用方 |
|------|----------|--------|
| `get_album(album_id)` | `SELECT` by PK | `layout_service` |
| `upsert_album(album)` | `INSERT ... ON CONFLICT UPDATE` | `layout_service` |
| `get_task(task_id)` | `SELECT` by PK | `layout_service` |
| `insert_task(task)` | `INSERT` | `layout_service` / `operation_service` |
| `update_task(task)` | `UPDATE` by PK | `layout_service` |
| `find_running_layout_tasks(album_id)` | `SELECT` with WHERE 联合索引 | `layout_service` |
| `get_layout(album_id, version)` | `SELECT` by 联合 PK | `layout_service` |
| `upsert_layout(layout)` | `INSERT ... ON CONFLICT UPDATE` | `layout_service` |
| `get_idempotency(scope)` | `SELECT` by PK | `layout_service` |
| `set_idempotency(scope, task_id)` | `INSERT` | `layout_service` |
| `insert_operation(operation)` | `INSERT` | `operation_service` |

### 4.4 依赖注入改造

**现状**（直接 import 全局 store）：

```python
# services/layout_service.py
from pixelpress_backend.repositories.memory import store

class LayoutService:
    def ensure_album(self, album_id: str) -> AlbumState:
        album = store.albums.get(album_id)  # 直接访问全局变量
```

**改造后**（构造注入仓库）：

```python
# services/layout_service.py
class LayoutService:
    def __init__(self, repo: "Repository"):
        self.repo = repo

    def ensure_album(self, album_id: str) -> AlbumState:
        album = self.repo.get_album(album_id)  # 通过仓库接口
```

```python
# api/dependencies.py
from pixelpress_backend.repositories.postgres import PostgresRepository

def get_repository():
    return PostgresRepository(session_factory)
    # 测试时替换为 MemoryRepository

def get_layout_service(repo=Depends(get_repository)):
    return LayoutService(repo)
```

---

## 5. 同步 vs 异步选择

| 方案 | 依赖 | 优点 | 缺点 |
|------|------|------|------|
| **同步** | `sqlalchemy` + `psycopg2-binary` | 改动最小，服务层方法签名不变，LangGraph 节点本就是同步函数 | FastAPI 线程会被数据库查询阻塞 |
| **异步** | `sqlalchemy[asyncio]` + `asyncpg` | 不阻塞事件循环，LangGraph 支持 `ainvoke()` | 所有服务层方法需改为 `async/await`，测试也需改造 |

> **已确认 #1**：选同步方案。

### 5.1 上线后需要改异步吗？

**大概率不需要。** 引入 Dramatiq 消息队列后，FastAPI 线程只做轻量的校验和 CRUD：

| FastAPI 线程的工作 | 耗时 | 需要 async 吗 |
|---------------------|------|:---:|
| POST 请求校验 + DB 写入 + 入队 | <50ms | 不需要 |
| GET 查询任务/相册状态 | <10ms | 不需要 |
| 返回 JSON | 瞬时 | 不需要 |

所有重任务都在 Worker 进程独立运行（LangGraph 流水线、特征提取、渲染、PDF 导出），与 FastAPI 线程无关。FastAPI 线程永远不会被长时间阻塞。

**只在以下场景才需要异步**（当前项目不涉及）：
- SSE/WebSocket 实时进度推送（长连接）
- 直接通过 FastAPI 接收大文件上传
- 1000+ 并发同时请求

### 5.2 如果以后真要改

改动量约 50-80 行，一个下午可完成：

| 改动层 | 内容 |
|--------|------|
| 仓库层 | 加一套 `async` 方法，旧方法可保留 |
| 服务层 | 方法加 `async`，DB 调用加 `await` |
| 路由层 | 函数加 `async` |
| 测试 | 加 `@pytest.mark.asyncio` |
| LangGraph | `invoke()` 改为 `ainvoke()` |

---

## 6. SQLite 开发模式

| 方案 | 优点 | 缺点 |
|------|------|------|
| **仅支持 PostgreSQL** | 与生产环境一致，JSONB、UPSERT 等特性原生支持 | 每人需安装 PostgreSQL |
| **同时支持 SQLite** | 本地零配置，`pip install` 即可开发 | SQLite 不支持部分 PostgreSQL 语法（JSONB 用 TEXT 替代，UPSERT 语法不同），需维护两套方言 |

> **待确认 #2**：是否支持 SQLite 作为本地开发替代？

如果选 SQLite 兼容，仓库层需要针对不同方言写差异化的 SQL（或使用 SQLAlchemy 方言自适应，但 JSONB ↔ TEXT 转换需额外处理）。

---

## 7. 配置项新增

`config.py` 新增：

```python
class Settings(BaseSettings):
    # ... 现有配置
    database_url: str = "postgresql://postgres:postgres@localhost:5432/pixelpress"
```

`.env.example` 新增：

```env
# 数据库连接
PIXELPRESS_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/pixelpress
# 本地开发可选 SQLite:
# PIXELPRESS_DATABASE_URL=sqlite:///pixelpress.db
```

---

## 8. 依赖新增

```toml
# pyproject.toml
dependencies = [
    # ... 现有
    "sqlalchemy>=2.0,<3.0",
    "psycopg2-binary>=2.9,<3.0",
    "alembic>=1.13,<2.0",
]
```

如果选异步方案，替换 `psycopg2-binary` 为 `asyncpg`，并添加 `sqlalchemy[asyncio]`。

---

## 9. Alembic 使用指南

### 9.1 基本概念

```
models.py              迁移脚本                  数据库
─────────              ────────                  ──────
定义表结构     →      自动生成 SQL   →           执行 DDL
(Python ORM)    alembic revision      alembic upgrade head
                --autogenerate
```

Alembic **不会随容器启动自动建表**，需要开发人员手动执行命令。但它的核心价值是用 Python 代码定义表结构，然后**自动对比差异生成迁移脚本**，不需要手写 SQL。

### 9.2 常用命令速查

```powershell
# --- 日常开发流程 ---

# 1. 启动数据库（首次或每次开发前）
docker compose up -d

# 2. 将当前迁移应用到数据库（建表或更新表）
uv run alembic upgrade head

# 3. 改了 models.py 后，自动生成新迁移脚本
uv run alembic revision --autogenerate -m "描述你改了什么"

# 4. 再次应用到数据库
uv run alembic upgrade head


# --- 其他常用命令 ---

# 查看当前数据库处于哪个迁移版本
uv run alembic current

# 查看所有迁移版本历史
uv run alembic history

# 回滚到上一个版本
uv run alembic downgrade -1

# 回滚到指定版本
uv run alembic downgrade abc123

# 生成空迁移脚本（不加 --autogenerate，手写 upgrade/downgrade）
uv run alembic revision -m "手动迁移描述"
```

### 9.3 完整示例：新增一个字段

假设要往 `albums` 表加一个 `cover_url` 字段：

```python
# 1. 修改 db/models.py
class AlbumModel(Base):
    # ... 现有字段
    cover_url = Column(String(512), nullable=True)  # 新增
```

```powershell
# 2. 自动生成迁移脚本
uv run alembic revision --autogenerate -m "add cover_url to albums"
```

Alembic 自动生成 `migrations/versions/xxxx_add_cover_url_to_albums.py`：

```python
def upgrade():
    op.add_column('albums', sa.Column('cover_url', sa.String(512), nullable=True))

def downgrade():
    op.drop_column('albums', 'cover_url')
```

```powershell
# 3. 应用到数据库
uv run alembic upgrade head
```

### 9.4 自动生成的迁移脚本长什么样（首次初始化示例）

执行 `alembic revision --autogenerate -m "initial schema"` 后，自动生成的迁移文件大致如下：

```python
"""initial schema

Revision ID: a1b2c3d4e5f6
Create Date: 2026-06-03 12:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = None


def upgrade() -> None:
    # 自动生成 5 张表的 CREATE TABLE 语句
    op.create_table('albums',
        sa.Column('album_id', sa.String(64), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='draft'),
        sa.Column('current_layout_version', sa.Integer(), nullable=True),
        sa.Column('latest_completed_task_id', sa.String(64), nullable=True),
        sa.Column('allow_preview', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('allow_export', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('allow_order', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('feature_status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('album_id')
    )
    # ... task_runs、book_layouts、user_operations、idempotency_keys 同理


def downgrade() -> None:
    op.drop_table('idempotency_keys')
    op.drop_table('user_operations')
    op.drop_table('book_layouts')
    op.drop_table('task_runs')
    op.drop_table('albums')
```

### 9.5 工作流总结

```
    ┌──────────────┐
    │ 改 models.py │ ← 用 Python ORM 类定义/修改表结构
    └──────┬───────┘
           ↓
    ┌──────────────────────┐
    │ alembic revision     │ ← 自动生成迁移脚本（自动对比差异）
    │ --autogenerate -m "" │
    └──────┬───────────────┘
           ↓
    ┌──────────────┐
    │ 检查迁移脚本  │ ← 人工审核自动生成的 SQL 是否正确
    └──────┬───────┘
           ↓
    ┌──────────────┐
    │ alembic      │ ← 执行建表/改表
    │ upgrade head │
    └──────────────┘
```

### 9.6 与 init.sql 方式的对比

| | init.sql | Alembic |
|------|----------|---------|
| 表结构定义 | 手写 SQL | `models.py`（Python） |
| 建表时机 | 容器首次启动自动执行 | 手动执行 `alembic upgrade head` |
| 改表操作 | 手写 `ALTER TABLE` | 改 `models.py` → 自动生成迁移 |
| 版本回滚 | 不支持 | `alembic downgrade -1` |
| 团队协作 | 需同步 SQL 文件 | 迁移脚本提交 Git，`upgrade head` 即可 |
| 学习成本 | 低（会 SQL 就行） | 中（需了解 ORM + Alembic 命令） |

---

## 10. 测试策略

| 测试类型 | 方案 |
|----------|------|
| **单元测试**（5 个现有用例） | 继续使用 `MemoryStore`，不依赖数据库。已有测试无需修改 |
| **仓库层单元测试**（新增） | 用 SQLite 内存模式（`:memory:`）创建临时数据库，测试每个 CRUD 方法 |
| **集成测试**（新增） | 可选，用 Docker 启动临时 PostgreSQL 容器 |

### 测试数据库配置

```python
# tests/conftest_db.py
import pytest
from sqlalchemy import create_engine
from pixelpress_backend.db.base import Base
from pixelpress_backend.repositories.postgres import PostgresRepository

@pytest.fixture
def repo():
    """每个测试用例创建独立的 SQLite 内存数据库"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return PostgresRepository(engine)
```

---

## 11. 实施步骤

| 步骤 | 内容 | 涉及文件 | 预计影响 |
|------|------|----------|----------|
| **1. 安装依赖** | 添加 `sqlalchemy`、`psycopg2-binary`、`alembic` 到 `pyproject.toml`，运行 `uv sync` | `pyproject.toml` | 无 |
| **2. 创建 db 模块** | 编写 `engine.py`、`base.py`、`models.py`（5 个 ORM 模型 + 转换方法） | `db/`（新建） | 无 |
| **3. 编写 PostgresRepository** | 实现 11 个仓库方法，替换 `MemoryStore` 的字典操作 | `repositories/postgres.py`（新建） | 无 |
| **4. 配置 Alembic** | 初始化 Alembic，生成 0001 初始迁移 | `migrations/`（新建） | 无 |
| **5. 改造依赖注入** | `LayoutService` 和 `OperationService` 改为构造注入仓库 | `services/`、`api/dependencies.py` | 中等 |
| **6. 运行测试验证** | 现有 5 个测试通过 + 新增仓库层测试 | `tests/` | 验证 |

---

## 12. 待确认事项

| # | 问题 | 选项 | 建议 |
|---|------|------|------|
| 1 | 同步还是异步？ | A. 同步 `psycopg2` / B. 异步 `asyncpg` | **A（同步）**，改动小，当前无需高并发 |
| 2 | 是否支持 SQLite 本地开发？ | A. 仅 PostgreSQL / B. 同时支持 SQLite | 待讨论（需权衡维护成本 vs 开发便利） |
| 3 | 何时执行？ | A. 立即 / B. 等另外两位对齐方案 | 待讨论 |
