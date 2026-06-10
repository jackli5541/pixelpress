-- PixelPress 初始表结构
-- 容器首次启动时自动执行（docker-entrypoint-initdb.d）

CREATE TABLE IF NOT EXISTS albums (
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

CREATE TABLE IF NOT EXISTS task_runs (
    task_id             VARCHAR(64) PRIMARY KEY,
    album_id            VARCHAR(64) NOT NULL REFERENCES albums(album_id),
    task_type           VARCHAR(30) NOT NULL,
    status              VARCHAR(20) NOT NULL DEFAULT 'queued',
    idempotency_key     VARCHAR(128) NOT NULL UNIQUE,
    base_version        INTEGER,
    result_version      INTEGER,
    error_code          VARCHAR(50),
    degrade_reasons     JSONB DEFAULT '[]',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_task_album_type_status ON task_runs(album_id, task_type, status);

CREATE TABLE IF NOT EXISTS book_layouts (
    album_id            VARCHAR(64) NOT NULL REFERENCES albums(album_id),
    version             INTEGER NOT NULL,
    status              VARCHAR(20) NOT NULL DEFAULT 'draft',
    base_version        INTEGER,
    is_partial          BOOLEAN NOT NULL DEFAULT FALSE,
    pages               JSONB DEFAULT '[]',
    chapters            JSONB DEFAULT '[]',
    score_snapshot      JSONB DEFAULT '{}',
    generation_meta     JSONB DEFAULT '{}',
    render_snapshot     JSON