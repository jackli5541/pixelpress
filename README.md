# Pixpress1 - AI 智能相册排版系统

基于 AI 的相册书自动排版系统，帮助用户将照片快速生成精美相册书，支持从上传到导出 PDF 的一站式流程。

## 核心流程

```mermaid
flowchart LR
    A["创建项目"] --> B["上传照片"]
    B --> C["照片清洗"]
    C --> D["章节聚类"]
    D --> E["页面规划"]
    E --> F["排版渲染"]
    F --> G["导出 PDF"]
```

### 功能模块

| 模块 | 说明 |
|------|------|
| 项目与上传 | 创建相册、选择规格与风格、批量上传照片 |
| 照片清洗 | AI 分析照片质量，识别重复图与低质量图，推荐保留结果 |
| 章节聚类 | 按时间/地点/事件自动分组章节，支持重命名、合并与拆分 |
| 页面规划 | 自动分页、智能匹配版式模板，支持手动调整 |
| 排版渲染 | HTML 渲染排版预览，支持全册预览与单页微调 |
| 导出 | 生成印刷规格 PDF（300 DPI，CMYK），支持下载 |

## 技术栈

| 层次 | 技术 |
|------|------|
| 前端 | Vue 3 + TypeScript + Vite + Vue Router + Pinia |
| UI 框架 | Tailwind CSS + Vant（用户端）+ Ant Design Vue（管理端） |
| 后端 | Python 3.11 + FastAPI |
| 异步任务 | ARQ + Redis |
| 数据库 | PostgreSQL |
| ORM | SQLAlchemy 2.0 |
| 对象存储 | MinIO / S3 / Local artifact storage |
| AI 服务 | 可配置 Provider（当前代码以 openai-compatible 配置链路为主） |
| PDF 导出 | Playwright（HTML → PDF 高保真渲染） |

## 系统架构

```mermaid
flowchart TB
    subgraph Frontend["前端层"]
        U["用户端 H5<br/>Vue 3 + Vant"]
        A["管理后台<br/>Vue 3 + Ant Design Vue"]
    end

    subgraph Backend["后端层 (Python 3.11)"]
        API["FastAPI API"]
        W["Celery Worker"]
        subgraph Engine["引擎层"]
            E1["清洗引擎"]
            E2["聚类引擎"]
            E3["排版引擎"]
            E4["导出引擎"]
        end
        W --> Engine
    end

    subgraph Data["数据层"]
        PG["PostgreSQL"]
        R["Redis"]
        M["MinIO / S3"]
    end

    U --> API
    A --> API
    API --> PG
    API --> R
    API --> M
    API --> W
    Engine --> PG
    Engine --> M
```

## 项目结构

```
pixpress1/
├── backend/                    # 后端服务
│   ├── app/
│   │   ├── main.py             # FastAPI 应用入口
│   │   ├── api/                # API 路由层
│   │   ├── core/               # 配置管理
│   │   ├── common/             # 通用模块（响应格式、枚举）
│   │   ├── engines/            # 核心引擎层
│   │   │   ├── cleaning_engine/    # 照片清洗引擎
│   │   │   ├── chapter_engine/     # 章节聚类引擎
│   │   │   ├── layout_engine/      # 排版引擎
│   │   │   └── export_engine/      # PDF 导出引擎
│   │   ├── modules/            # 业务模块
│   │   │   ├── album/          # 相册管理
│   │   │   ├── photo/          # 照片管理
│   │   │   ├── cleaning/       # 照片清洗
│   │   │   ├── chapter/        # 章节管理
│   │   │   ├── layout/         # 排版管理
│   │   │   ├── export/         # 导出管理
│   │   │   └── user/           # 用户模块
│   │   └── storage/            # 存储层（文件、内存）
│   ├── requirements.txt
│   └── .env.example
├── frontend/                   # 前端应用
│   └── src/
│       ├── app/                # 应用级配置（路由、Provider）
│       ├── features/           # 功能页面
│       │   ├── project-upload/     # 项目创建 & 上传
│       │   ├── photo-cleaning/     # 照片清洗
│       │   ├── chapter-clustering/ # 章节聚类
│       │   ├── page-planning/      # 页面规划
│       │   └── export-order/       # 导出中心
│       ├── modules/admin/      # 管理后台
│       └── shared/             # 共享组件、API 封装、类型定义
├── start.bat                  # Windows 一键启动脚本
└── .env                       # 环境变量
```

## 快速开始

### Docker 运行与测试说明（推荐）

当前项目默认以 Docker 作为主要运行方式，日常开发和验证建议优先使用：

- `compose.prod.yml`：主运行栈（web / backend / worker / postgres / redis / minio）
- `compose.test.yml`：测试栈（backend-test / postgres-test / redis-test）
- `start.bat`：Windows 下统一入口

目前已经支持：

- 预览 HTML 走存储 artifact
- 预览图片走签名 render asset URL
- 导出 PDF 走 Playwright
- render / export / artifact cleanup 的 Docker 定向测试

### 当前实现状态（A 任务）

当前仓库已完成 A 任务的主线落地，具备以下能力：

- **A1**：PostgreSQL + SQLAlchemy Async + Alembic 骨架
- **A2**：统一文件存储抽象，支持 Local / MinIO 实现
- **A3**：注册 / 登录 / JWT 鉴权 + owner/admin 基础访问控制
- 前端已同步：登录/注册入口、受保护图片显示、带 token 的导出与任务访问

### 前置依赖

- **Docker Desktop**（推荐，当前默认开发方式）
- **Node.js** 18+
- **Python** 3.11+

> 当前推荐通过 `docker compose` 提供 PostgreSQL / Redis / MinIO，避免本地手工安装依赖。

### Docker Compose 启动主运行栈

项目根目录当前主要使用：

- `compose.prod.yml`：主运行栈
- `compose.test.yml`：测试栈

Windows 下推荐直接使用：

```bash
start.bat
```

当前 `start.bat` 会启动主容器栈，并提供以下常用命令：

```bash
start.bat              # 启动主运行栈
start.bat pull         # 拉取主运行栈和测试栈镜像
start.bat ps           # 查看主运行栈状态
start.bat logs         # 查看主运行栈日志
start.bat down         # 停止主运行栈
start.bat restart      # 重建并重启主运行栈
```

主运行栈启动后可访问：

- 前端 App：`http://127.0.0.1/`
- 后端 API：`http://127.0.0.1/api/v1`
- 健康检查：`http://127.0.0.1/api/v1/health`
- API 文档：`http://127.0.0.1/docs`

### Docker 测试栈与专项验证

项目已提供独立的 Docker 测试栈：

- `backend-test`
- `postgres-test`
- `redis-test`

推荐命令：

```bash
start.bat test         # 运行 backend 全量集成测试（Docker）
start.bat test-render  # 运行 render / preview / export / artifact cleanup 专项测试
start.bat test-up      # 启动测试依赖容器
start.bat test-ps      # 查看测试栈状态
start.bat test-logs    # 查看测试栈日志
start.bat test-down    # 停止并删除测试栈及测试卷
```

`start.bat test-render` 当前覆盖：

- render artifact 落盘与清理
- album invalidation
- preview 签名图片访问
- page preview snippet 合同
- HTML / PDF 导出主链路

如需直接用 compose 命令：

```bash
docker compose -f compose.test.yml run --rm backend-test pytest tests/integration/test_async_task_flow.py tests/integration/test_render_artifact_invalidation.py tests/integration/test_render_artifact_cleanup.py tests/integration/test_legacy_api_contract.py tests/integration/test_preview_render_assets.py tests/integration/test_page_preview_snippet.py -q
```

### 手动启动

#### 1. 配置环境变量

```bash
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
```

`backend/.env` 推荐至少确认以下字段：

```env
DATABASE_URL=postgresql+psycopg://postgres:postgres@127.0.0.1:56432/pixpress1
TEST_DATABASE_URL=postgresql+psycopg://postgres:postgres@127.0.0.1:56432/pixpress1_test
REDIS_URL=redis://127.0.0.1:6379/0
MINIO_ENDPOINT=127.0.0.1:9100
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=pixpress1
MINIO_SECURE=false
STORAGE_BACKEND=local
AUTH_SECRET_KEY=change-me-in-production
```

说明：
- `STORAGE_BACKEND=local`：使用本地文件存储
- `STORAGE_BACKEND=minio`：切换为 MinIO 存储

#### 2. 启动后端

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -r requirements.txt
python -m playwright install chromium
python scripts/run_dev_server.py
```

#### 3. 启动前端

```bash
cd frontend
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

### 登录与验证

当前前端顶部已提供：

- 注册
- 登录
- 退出登录

建议启动后先：
1. 注册用户
2. 登录用户
3. 再进入相册创建 / 上传 / 清洗 / 导出等流程

完整运行与验收步骤见：

- `实施计划/A任务运行验证说明.md`

## API 概览

所有 API 均以 `/api/v1` 为前缀，统一响应格式：

```json
{
  "code": 0,
  "message": "success",
  "request_id": "uuid",
  "data": {}
}
```

### 主要接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/auth/register` | 注册用户 |
| POST | `/api/v1/auth/login` | 登录并获取 JWT |
| GET  | `/api/v1/users/me` | 获取当前用户 |
| POST | `/api/v1/albums` | 创建相册（需登录） |
| POST | `/api/v1/albums/{id}/photos/upload` | 上传照片（需登录） |
| GET  | `/api/v1/albums/{album_id}/photos/{photo_id}/content` | 获取受保护图片内容 |
| POST | `/api/v1/albums/{id}/clean` | 触发清洗（需登录） |
| POST | `/api/v1/albums/{id}/cluster` | 触发章节聚类（需登录） |
| POST | `/api/v1/albums/{id}/plan` | 触发页面规划（需登录） |
| POST | `/api/v1/albums/{id}/render` | 触发排版渲染（需登录） |
| GET  | `/api/v1/albums/{id}/preview` | 获取排版预览（需登录） |
| POST | `/api/v1/albums/{id}/export` | 导出 HTML/PDF（需登录） |
| GET  | `/api/v1/albums/{id}/export/download/{export_id}` | 下载导出文件（需登录） |
| GET  | `/api/v1/tasks/{id}` | 查询任务状态（admin） |

完整接口文档见 Swagger UI：http://127.0.0.1:8000/docs

## 相册状态流转

```mermaid
stateDiagram-v2
    [*] --> draft
    draft --> uploaded
    uploaded --> cleaned
    cleaned --> clustered
    clustered --> planned
    planned --> rendered
    rendered --> exported
    exported --> [*]

    draft --> failed
    uploaded --> failed
    cleaned --> failed
    clustered --> failed
    planned --> failed
    rendered --> failed
    exported --> failed
```

每个阶段由对应的异步任务驱动，前端通过任务状态接口（`GET /api/v1/tasks/{id}`）轮询进度。

## 环境变量说明

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `APP_NAME` | 应用名称 | `Pixpress1 API` |
| `APP_ENV` | 运行环境 | `development` |
| `APP_HOST` | 绑定地址 | `127.0.0.1` |
| `APP_PORT` | 服务端口 | `8000` |
| `DATABASE_URL` | 数据库连接 | `postgresql+psycopg://...` |
| `TEST_DATABASE_URL` | 测试数据库连接 | `postgresql+psycopg://..._test` |
| `REDIS_URL` | Redis 连接 | `redis://127.0.0.1:6379/0` |
| `MINIO_ENDPOINT` | MinIO 地址 | `127.0.0.1:9000` |
| `MINIO_BUCKET` | MinIO bucket | `pixpress1` |
| `MINIO_SECURE` | MinIO 是否 HTTPS | `false` |
| `STORAGE_BACKEND` | 存储后端 `local|minio` | `local` |
| `AUTH_SECRET_KEY` | JWT 密钥 | `change-me-in-production` |
| `UPLOADS_DIR` | 本地上传目录 | `uploads` |
