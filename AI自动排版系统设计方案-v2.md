# AI 自动排版系统设计方案
## 1. 总体判断
基于当前 PRD，这个项目真正的壁垒不在"会不会排版"，而在于能否把"照片理解 -> 叙事编排 -> 印刷级输出"做成一条稳定、可控、可复用的流水线。

+ `AI 自动排版` 不适合做成纯生成式黑盒，更适合做成"规则约束 + 视觉模型评分 + 候选搜索"的混合系统。
+ 项目一期 MVP 应优先追求"稳定出书"和"印刷可交付"，而不是一开始追求特别强的创意感。
+ 真正影响体验的不是单页好不好看，而是"整本书是否有节奏、有故事线、用户是否只需少量微调"。

## 2. AI 自动排版算法设计
### 2.1 目标定义
把 `50-300` 张照片转成一本"可读、可印、可微调"的相册书。核心不是单页美观，而是整本书的叙事节奏、主体突出和印刷稳定性。

### 2.2 推荐范式
采用 `规则约束 + CV/多模态理解 + 候选搜索 + 美学评分` 的混合方案，不建议直接用大模型端到端生成页面坐标。

### 2.3 输入数据
每张照片应沉淀为统一特征对象，建议包含以下字段：

+ `EXIF` 信息
+ 图像尺寸与方向
+ 清晰度、曝光、闭眼、模糊等质量分
+ 人脸框、主体框
+ 显著性热力图
+ embedding 向量
+ 重复指纹
+ 场景标签
+ 人物 ID

### 2.4 核心流程
建议拆成以下 5 层：

1. `照片清洗`
2. `章节聚类`
3. `页面规划`
4. `版式生成`
5. `全书评分`

### 2.5 详细流程说明
#### 照片清洗
+ 给每张图打质量分，不急着删图。
+ 仅对极差图和近重复图做剔除，其余图做排序降权。
+ 评分项建议包含：`清晰度`、`曝光`、`闭眼`、`重复度`、`人脸完整度`、`主体显著性`。

#### 章节聚类
+ 不建议只靠时间排序。
+ 应融合 `时间/地点 + embedding + 人脸身份 + 场景分类` 共同切 chapter。
+ 年度册按月份优先，活动册按事件优先。

#### 页面规划
这是最容易被忽视但最重要的一层。它负责决定：

+ 整本书总页数
+ 每章页数
+ 哪些照片适合跨页
+ 哪些页面适合多图拼版
+ 哪些照片作为章节扉页或收束页

这一步更像"编辑决策"，不只是视觉布局。

#### 版式生成
不建议从零生成坐标，而是准备一套参数化版式语法，例如：

+ `单图满版`
+ `双图对开`
+ `三图叙事`
+ `九宫格摘要`
+ `章节扉页`

再根据横竖比、主体位置、安全裁切区自动填充。

#### 裁切求解
+ 每张图输出 `saliency map + face boxes + subject boxes + safe crop window`。
+ 自动裁切时不能切脸、切主体、切高权重视觉中心。
+ 任何裁切都应受安全区约束。

#### 全书评分
排版结果不能只看单页，而要看全书节奏。建议同时优化：

+ 主体突出
+ 页面平衡
+ 章节节奏
+ 相邻页差异度
+ 留白一致性
+ 印刷安全

#### 五层模块工程化定义（输入/输出契约）
为便于后续拆分为 LangGraph 节点、异步任务和可测试模块，建议将五层统一定义为"纯输入 -> 处理 -> 输出"的标准接口。每层都只依赖上游结果和显式约束，不直接读取前端状态。

##### 1. 照片清洗层（Photo Cleaning）
**职责**：

+ 校验照片可用性，过滤损坏文件、极低分辨率、格式异常图片
+ 计算质量分、重复度、人物完整度、主体显著性等基础指标
+ 产出保留/降权/剔除建议，但默认仅剔除极差图和强重复图
+ 为后续聚类和页面规划准备稳定的候选照片集合

**关键处理内容**：

+ 文件完整性检查：是否可解码、尺寸是否满足最小印刷要求
+ 质量评估：清晰度、曝光、闭眼、噪点、模糊、主体完整度
+ 重复检测：感知哈希 + embedding 相似度 + 连拍时间窗
+ 排序降权：对不删除的边缘照片打低优先级，避免直接丢失用户素材

**输入参数**：

```json
{
  "album_id": "string",
  "scene_mode": "annual | event",
  "book_size": "A4_square",
  "photo_assets": [
    {
      "photo_id": "p001",
      "image_url": "string",
      "width": 4032,
      "height": 3024,
      "orientation": "landscape | portrait",
      "exif": {
        "captured_at": "2026-05-01T10:00:00Z",
        "gps": "optional"
      },
      "features": {
        "embedding": "optional vector ref",
        "face_boxes": [],
        "subject_boxes": [],
        "saliency_map": "optional ref"
      }
    }
  ],
  "constraints": {
    "must_include": ["p005"],
    "must_exclude": ["p012"],
    "hero_person_id": "person_001"
  }
}
```

**输出参数**：

```json
{
  "album_id": "string",
  "valid_photos": [
    {
      "photo_id": "p001",
      "quality_score": 0.91,
      "duplicate_score": 0.08,
      "saliency_score": 0.76,
      "face_integrity_score": 0.95,
      "rank_weight": 1.0,
      "decision": "keep | deprioritize | drop",
      "drop_reason": null
    }
  ],
  "dropped_photos": [
    {
      "photo_id": "p099",
      "reason": "corrupted | strong_duplicate | too_small"
    }
  ],
  "cleaning_summary": {
    "input_count": 150,
    "valid_count": 138,
    "dropped_count": 12,
    "duplicate_groups": 9
  }
}
```

##### 2. 章节聚类层（Chapter Clustering）
**职责**：

+ 将清洗后的照片按"事件或时间段"切分为多个章节
+ 给每个章节生成标题候选、封面候选和章节摘要特征
+ 识别章节边界，避免将同一事件拆散或将不同事件硬拼在一起

**关键处理内容**：

+ 聚类信号融合：时间、地点、embedding、人物共现、场景分类
+ 章节边界检测：长时间间隔、场景切换、人物组合变化
+ 模式差异：年度册以时间主序，活动册以事件主序
+ 章节命名准备：生成章节标签、代表图、主角人物列表

**输入参数**：

```json
{
  "album_id": "string",
  "scene_mode": "annual | event",
  "valid_photos": [
    {
      "photo_id": "p001",
      "captured_at": "2026-05-01T10:00:00Z",
      "location_cluster": "loc_01",
      "embedding_ref": "vec_001",
      "person_ids": ["person_001", "person_003"],
      "scene_tags": ["beach", "sunset"],
      "rank_weight": 1.0
    }
  ],
  "constraints": {
    "chapter_count_hint": 8,
    "hero_person_id": "person_001"
  }
}
```

**输出参数**：

```json
{
  "album_id": "string",
  "chapters": [
    {
      "chapter_id": "c001",
      "order": 1,
      "title_candidate": "海边一日",
      "photo_ids": ["p001", "p002", "p003"],
      "cover_photo_id": "p001",
      "key_person_ids": ["person_001"],
      "scene_tags": ["beach", "sunset"],
      "time_range": {
        "start": "2026-05-01T10:00:00Z",
        "end": "2026-05-01T19:00:00Z"
      },
      "cluster_confidence": 0.88
    }
  ],
  "clustering_summary": {
    "chapter_count": 8,
    "avg_photos_per_chapter": 18,
    "low_confidence_chapters": ["c007"]
  }
}
```

##### 3. 页面规划层（Pagination Planning）
**职责**：

+ 决定整本书的页数预算、章节页数预算和页面节奏
+ 为每页分配"叙事角色"，如扉页、高潮页、摘要页、收束页
+ 选出跨页候选、多图拼版候选、单图主视觉候选
+ 先做"编辑级结构决策"，再交给版式生成求解几何布局

**关键处理内容**：

+ 全书预算：总页数、章节页数、每章密度
+ 照片角色选择：hero 图、support 图、detail 图、appendix 图
+ 节奏控制：起势页、转场页、高潮页、收束页的分布
+ 约束处理：must include、must exclude、不要跨页、主角曝光率

**输入参数**：

```json
{
  "album_id": "string",
  "book_size": "A4_square",
  "binding": "hardcover",
  "style": "minimal",
  "chapters": [
    {
      "chapter_id": "c001",
      "title_candidate": "海边一日",
      "photo_ids": ["p001", "p002", "p003"],
      "cover_photo_id": "p001",
      "scene_tags": ["beach"]
    }
  ],
  "photo_pool": [
    {
      "photo_id": "p001",
      "quality_score": 0.91,
      "orientation": "landscape",
      "rank_weight": 1.0,
      "is_duplicate": false
    }
  ],
  "constraints": {
    "min_pages": 20,
    "max_pages": 60,
    "avoid_spread": false,
    "hero_person_id": "person_001"
  }
}
```

**输出参数**：

```json
{
  "album_id": "string",
  "page_plan": {
    "total_pages": 32,
    "chapter_page_budgets": [
      {
        "chapter_id": "c001",
        "start_page": 1,
        "end_page": 4,
        "page_count": 4
      }
    ],
    "planned_pages": [
      {
        "page_id": "page_001",
        "chapter_id": "c001",
        "page_role": "chapter_opening | hero | collage | ending",
        "candidate_photo_ids": ["p001"],
        "layout_family": "single_full_bleed",
        "is_spread": false,
        "text_need": "chapter_title | caption | none"
      }
    ]
  },
  "planning_summary": {
    "selected_photo_count": 96,
    "unused_photo_count": 42,
    "spread_count": 3
  }
}
```

##### 4. 版式生成层（Layout Generation）
**职责**：

+ 将页面规划结果映射到具体模板，并求解每个槽位的几何参数
+ 基于安全裁切区、主体框、人脸框完成图片填充和裁切
+ 生成可渲染的 `PageLayout` 结构，供预览、导出和微调使用

**关键处理内容**：

+ 模板选择：根据页面角色和照片组合选择 DSL 模板
+ 槽位求解：x/y/width/height/z-index、留白、对齐、边距
+ 裁切求解：基于 safe crop window、saliency、face boxes 防止错误裁切
+ 文本占位：为章节标题、短标语、页内文案预留文本框

**输入参数**：

```json
{
  "album_id": "string",
  "book_size": "A4_square",
  "style": "minimal",
  "page_plan": {
    "planned_pages": [
      {
        "page_id": "page_001",
        "page_role": "chapter_opening",
        "candidate_photo_ids": ["p001"],
        "layout_family": "single_full_bleed",
        "text_need": "chapter_title"
      }
    ]
  },
  "layout_templates": [
    {
      "template_id": "tpl_single_full_bleed",
      "family": "single_full_bleed",
      "slot_count": 1
    }
  ],
  "photo_features": [
    {
      "photo_id": "p001",
      "width": 4032,
      "height": 3024,
      "face_boxes": [],
      "subject_boxes": [],
      "safe_crop_window": {
        "x": 0.08,
        "y": 0.05,
        "w": 0.84,
        "h": 0.9
      }
    }
  ]
}
```

**输出参数**：

```json
{
  "album_id": "string",
  "page_layouts": [
    {
      "page_id": "page_001",
      "template_id": "tpl_single_full_bleed",
      "layout_score": 0.87,
      "slots": [
        {
          "slot_id": "slot_01",
          "photo_id": "p001",
          "frame": {
            "x": 0.0,
            "y": 0.0,
            "w": 1.0,
            "h": 1.0
          },
          "crop": {
            "x": 0.05,
            "y": 0.02,
            "w": 0.9,
            "h": 0.96
          }
        }
      ],
      "text_blocks": [
        {
          "block_id": "title_01",
          "type": "chapter_title",
          "frame": {
            "x": 0.08,
            "y": 0.8,
            "w": 0.4,
            "h": 0.08
          }
        }
      ],
      "render_hints": {
        "background": "#FFFFFF",
        "bleed_mm": 3
      }
    }
  ],
  "generation_summary": {
    "page_count": 32,
    "fallback_page_count": 2
  }
}
```

##### 5. 全书评分层（Book Scoring）
**职责**：

+ 对整本书进行硬规则校验和软评分
+ 判断当前排版是否可直接输出，或需要回退到上游重排
+ 输出页面级和全书级问题列表，供自动纠错和用户微调使用

**关键处理内容**：

+ 硬规则检查：切脸、切主体、中缝风险、低清放大、出血安全
+ 软评分计算：节奏、统一性、多样性、留白舒适度、主角曝光率
+ 全书统计：连续同构页、章节密度失衡、跨页过多等问题
+ 回退建议：指出应回退到页面规划还是版式生成

**输入参数**：

```json
{
  "album_id": "string",
  "book_layout": {
    "pages": [
      {
        "page_id": "page_001",
        "template_id": "tpl_single_full_bleed",
        "slots": [],
        "text_blocks": []
      }
    ],
    "chapters": [
      {
        "chapter_id": "c001",
        "page_ids": ["page_001", "page_002"]
      }
    ]
  },
  "scoring_rules": {
    "hard_rules_enabled": true,
    "soft_weights": {
      "subject_salience": 0.2,
      "page_balance": 0.15,
      "story_coherence": 0.2,
      "layout_diversity": 0.15,
      "print_safety": 0.3
    }
  },
  "context": {
    "hero_person_id": "person_001",
    "scene_mode": "annual"
  }
}
```

**输出参数**：

```json
{
  "album_id": "string",
  "decision": "accept | retry_layout | retry_planning",
  "score_snapshot": {
    "hard_violations": [
      {
        "page_id": "page_008",
        "rule": "face_cut_by_gutter",
        "severity": "critical"
      }
    ],
    "soft_scores": {
      "subject_salience": 0.82,
      "page_balance": 0.76,
      "story_coherence": 0.8,
      "layout_diversity": 0.71,
      "print_safety": 0.93
    },
    "global_scores": {
      "overall": 0.81,
      "chapter_rhythm": 0.78,
      "hero_exposure": 0.86
    }
  },
  "repair_hints": [
    {
      "target": "page_008",
      "action": "regenerate_page_layout"
    },
    {
      "target": "chapter_c003",
      "action": "rebalance_page_budget"
    }
  ]
}
```

#### 五层之间的串联关系
建议统一约定以下中间对象，避免相邻层直接耦合内部实现：

+ `CleanedPhotoSet`：照片清洗层输出，供章节聚类和页面规划复用
+ `ChapterPlan[]`：章节聚类层输出，供页面规划使用
+ `PagePlan[]`：页面规划层输出，供版式生成使用
+ `PageLayout[]`：版式生成层输出，供评分、渲染、导出、微调使用
+ `ScoreSnapshot`：评分层输出，供 LangGraph 决策是否回退或进入 HITL

这样定义后，LangGraph 的每个节点都可以是"读取上游结构化结果 -> 产出下游结构化结果"的纯函数式节点，后续无论落地为单体服务、微服务还是异步任务队列，接口都相对稳定。

---

> 新增开始：优化1（排版引擎输入/输出契约）
>

---

### 2.6 排版引擎输入/输出契约
排版引擎作为核心服务，需要明确的接口契约，使前端和后端可并行开发。

#### 输入（POST /api/layout/generate）
```json
{
  "album_id": "相册书项目ID",
  "idempotency_key": "gen-20260603-001",
  "scene_mode": "annual | event",
  "book_size": "A4_square",
  "binding": "hardcover | softcover",
  "style": "minimal | retro | fresh",
  "photo_ids": ["p001", "p002", "..."],
  "photo_order": "upload_order | time_asc",
  "force_mode": "normal | slow_path",
  "constraints": {
    "must_include": ["p005"],
    "must_exclude": ["p012"],
    "hero_person_id": "person_001",
    "min_pages": 20,
    "max_pages": 60
  }
}
```

#### 输出（异步任务）
排版为异步任务，请求后返回 `task_id`，前端轮询结果：

```json
// 立即返回
{
  "task_id": "layout-task-abc123",
  "task_status": "queued",
  "album_status": "generating",
  "book_layout_version": null,
  "estimated_seconds": 20
}

// 轮询 GET /api/layout/status/:task_id 完成后返回
{
  "task_id": "layout-task-abc123",
  "task_status": "completed",
  "album_status": "reviewable",
  "result": {
    "book_layout": { /* BookLayout JSON，详见 5.4 节 */ },
    "thumbnail_urls": ["url1", "url2", "..."],
    "generation_meta": {
      "seed": 42,
      "pipeline_version": "1.0.0",
      "duration_ms": 18420,
      "photo_count": 150,
      "chapter_count": 8,
      "page_count": 32
    }
  }
}
```

#### 状态分层与幂等约定
为避免 `task status`、`book status`、`album status` 混用，推荐在 FastAPI + LangGraph 架构中明确区分 4 类状态：

+ **TaskState.status**：`queued | running | completed | failed | cancelled | timed_out | partial`
+ **FeatureState.status**：`pending | extracting | partial | ready | failed`
+ **Album.status**：`draft | generating | reviewable | locked | ordered | archived`
+ **BookLayout.status**：`draft | locked | exported`

约束如下：

+ `TaskState` 用于表达一次异步任务执行情况，不直接代表相册业务状态
+ `Album.status` 用于表达当前项目所处阶段，是否允许预览、锁定和下单
+ `BookLayout.status` 仅表达某个布局版本的冻结/导出状态，不用于表达"任务是否完成"
+ 所有写接口必须支持 `idempotency_key` 或等价操作 ID，防止重复点击或网络重试导致重复生成
+ 所有修改当前布局的写接口都必须带 `base_version`，若服务端当前版本已变化，应返回 `409 CONFLICT`

#### 部分完成结果约定
若排版链路因超时或下游服务异常仅返回部分结果，必须返回显式标记：

```json
{
  "task_id": "layout-task-abc123",
  "task_status": "partial",
  "album_status": "generating",
  "result": {
    "book_layout": {
      "version": 3,
      "status": "draft",
      "is_partial": true
    },
    "degrade_reasons": ["render_pending", "score_skipped"],
    "allow_preview": true,
    "allow_export": false,
    "allow_order": false
  }
}
```

#### 超时约定
| 场景 | 特征状态 | 排版耗时目标 | 超时阈值 |
| --- | --- | --- | --- |
| 正常流程 | 特征已预计算 | ≤ 20s | 30s |
| 首次上传 | 特征提取中 | ≤ 60s | 90s |
| 重排/微调 | 特征已缓存 | ≤ 5s | 15s |


#### 错误响应
```json
{
  "status": "failed",
  "error_code": "INSUFFICIENT_PHOTOS",
  "message": "照片数量不足，至少需要10张有效照片",
  "valid_photo_count": 5
}
```

---

<<< 新增结束

---

> 新增开始：优化7（流水线容错与降级）
>

---

### 2.7 流水线容错与降级
五层流水线中任何一层都可能因模型故障、数据异常等原因失败。需要逐层定义降级策略，确保"总能输出一本可用的书"。

| 流水线阶段 | 故障场景 | 降级策略 | 对用户的影响 |
| --- | --- | --- | --- |
| 照片清洗 | 质量评估模型加载失败 | 跳过质量评分，按上传顺序使用全部照片，仅剔除文件损坏的图 | 可能有模糊照片出现在书中 |
| 照片清洗 | EXIF 数据全部缺失 | 使用文件修改时间作为 fallback 时间戳 | 时间聚类准确性下降 |
| 章节聚类 | 场景分类模型超时 | 仅按时间排序切分章节，取消场景标签 | 章节标题变为"第1章/第2章"，无场景名 |
| 页面规划 | 有效照片数量 < 10 张 | 自动切换为"全幅单图"模式，每页1张照片 | 书本变薄，但版式仍然美观 |
| 页面规划 | 照片数量 > 500 张 | 按质量分从高到低取前 300 张，其余放入附录 | 质量最差的照片不会出现在正文 |
| 版式生成 | 所有版式模板均不匹配某照片 | 降级为通用"单图满版"版式，保留 3mm 出血 | 该页版式普通但不难看 |
| 版式生成 | 裁切安全区计算失败 | 使用图片中心 80% 区域作为默认安全区 | 可能存在轻微裁切不准确 |
| 全书评分 | 评分模型异常 | 跳过评分环节，直接使用第一版排版结果输出 | 排版效果可能不是最优的，但保证有结果 |
| 全书流程 | 排版总耗时超过阈值 | 返回已完成的部分结果 + "排版未完成"标记，支持用户继续等待或接受当前结果 | 用户可选择是否继续等待 |


**容错设计原则**：

+ **渐进降级**：宁可输出不完美但完整的结果，也不返回空白页
+ **用户知情**：降级发生时前端显示温和提示（如"部分照片未能自动分类，已按时间排列"），不展示技术错误
+ **可恢复**：降级不等于放弃，用户后续可重新触发完整流程
+ **不可误下单**：任何 `partial` 结果都不得进入 `locked`、`exported`、`ordered`
+ **禁止静默成功**：评分跳过、渲染未完成、导出参数不完整都必须显式写入 `degrade_reasons`

---

<<< 新增结束

---

---

> 新增开始：优化8（HITL人机协同干预点 + LangGraph编排）
>

---

### 2.8 HITL 人机协同干预点
#### 概述
排版流水线中有 4 个关键位置允许用户介入（Human-in-the-Loop），由浅到深分布在整个流程中。每个干预点都是可选的——用户可以直接确认跳过，AI 自动通过。

#### 干预点全景图
```latex
照片上传 → 特征提取
              ↓
         ┌────────┐
         │ 照 片  │
         │ 清 洗  │
         └───┬────┘
             ↓
         ┌────────┐
    ┌───→│ 章 节  │
    │    │ 聚 类  │
    │    └───┬────┘
    │        ↓
    │  ╔══════════════════╗
    │  ║ HITL #1：章节确认  ║  ← 用户审核章节划分（轻量级，可跳过）
    │  ╚════════┬═════════╝
    │           ↓
    │      ┌────────┐
    │      │ 页 面  │
    │      │ 规 划  │
    │      └───┬────┘
    │          ↓
    │      ┌────────┐
    │  ┌──→│ 版 式  │←──────────────┐
    │  │   │ 生 成  │               │
    │  │   └───┬────┘               │
    │  │       ↓                    │
    │  │   ┌────────┐               │
    │  │   │ 全 书  │               │
    │  │   │ 评 分  │               │
    │  │   └───┬────┘               │
    │  │       ↓                    │
    │  │  ╔════════════════════╗    │
    │  │  ║ HITL #2：全书预览确认 ║  │  ← 用户查看预览，微调页面（主战场）
    │  │  ╚════════┬═══════════╝    │
    │  │           ↓                │
    │  │      ┌────────┐            │
    │  │      │ 生 成  │            │
    │  │      │ 文 案  │            │
    │  │      └───┬────┘            │
    │  │          ↓                 │
    │  │     ╔══════════════╗       │
    │  │     ║ HITL #3：文案确认 ║   │  ← 用户修改标题/标语（轻量级）
    │  │     ╚════════┬═════╝       │
    │  │              ↓             │
    │  │          ╔══════════╗      │
    │  │          ║ 冻 结    ║      │
    │  │          ║ 下 单    ║      │
    │  │          ╚══════════╝      │
    │  │                            │
    │  └──── 评分不合格 → 重排 ──────┘
    │
    └──── 用户否定章节 → 重聚类 ──┘
```

#### HITL #1：章节确认（轻量级）
| 维度 | 内容 |
| --- | --- |
| **时机** | 章节聚类完成后、页面规划之前 |
| **用户操作** | 合并/拆分章节、重命名章节标题、删除某个章节、调整章节顺序 |
| **用户不操作** | 3 分钟后自动通过，进入页面规划 |
| **干预成本** | 低（只看章节结构，不看具体页面） |
| **典型场景** | AI 把"海滩"和"篝火晚会"拆成两章，用户改为合并为"海边一日" |


#### HITL #2：全书预览确认（主战场）⭐
| 维度 | 内容 |
| --- | --- |
| **时机** | 全书评分通过后、文案生成前 |
| **用户操作** | 换图、交换两页照片位置、修改文案、调整照片裁切范围、标记某页"不喜欢"触发局部重排、指定"主角人物"重新优化曝光率 |
| **干预深度** | 深，可触发局部重排和重评分 |
| **典型场景** | 用户发现第 8 页照片裁切不完美，点击调整 → 手动拖动裁切框 → 确认后仅重渲染该页 |


这是最核心的 HITL 点。用户在此处完成主要微调后，变更仅影响局部页面，不会触发全书重排。

#### HITL #3：文案确认（轻量级）
| 维度 | 内容 |
| --- | --- |
| **时机** | 文案生成后、最终下单前 |
| **用户操作** | 修改章节标题、编辑标语文字、切换文案风格 |
| **用户不操作** | 1 分钟后自动通过 |
| **干预成本** | 极低（只改文字，不涉及布局） |


#### HITL #4：下单最终确认（必过关卡）
| 维度 | 内容 |
| --- | --- |
| **时机** | 所有流程完成后 |
| **用户操作** | 确认全书无误 → 冻结版本（status 变为 `locked`）→ 提交订单 |
| **用户取消** | 状态重置为 `draft`，支持后续重新编辑 |
| **保险意义** | 印刷不可逆，这是防止误触下单的最后防线 |


#### HITL 对流水线的影响
| HITL 点 | 用户操作后 | 流程变化 |
| --- | --- | --- |
| #1 章节确认 | 改章节结构 | 回退到页面规划，页面规划/版式生成/评分重新执行 |
| #2 全书预览 | 换图/调裁切 | 仅重算当前页和相邻页的版式，局部评分 |
| #2 全书预览 | 指定"主角人物" | 回退到页面规划并重算评分；若页序和照片选择不变，再复用既有版式结果 |
| #3 文案确认 | 改文字 | 仅重新生成该章节文案，不影响任何页面布局 |
| #4 下单确认 | 确认 | 冻结 BookLayout，触发 PDF 导出和工厂下单 |


#### LangGraph 编排
HITL 的流程控制和状态管理推荐使用 **LangGraph** 作为编排引擎：

+ **条件边**：实现"评分不合格 → 回退到排版节点"等流程分支
+ **interrupt()**：在每个 HITL 点暂停图执行，等待用户操作后从 checkpoint 恢复
+ **Checkpointer**：内置状态持久化，断点续传不丢失进度
+ **Streaming**：向用户实时推送"正在聚类…正在排版…"等进度信息

LangGraph 仅负责**流程编排和状态机管理**，不执行模型推理。YOLO、FaceNet、CLIP 等模型推理应由 Python 异步 Worker 承载，渲染和 PDF 导出由独立服务完成。由于后端主架构确定为 `FastAPI + LangGraph`，一期不建议再引入 `BullMQ` 作为核心任务总线，优先使用 Python 生态内的任务队列或后台 Worker，降低跨语言队列协议复杂度。

#### MVP 建议
四个 HITL 点中，**MVP 优先实现 #2（全书预览确认）和 #4（下单确认）**。#1（章节确认）和 #3（文案确认）可在二期补充。

---

<<< 新增结束

---

## 3. 评分体系设计
### 3.1 硬规则
以下情况应强制降级或淘汰：

+ 人脸贴边
+ 中缝切脸
+ 主体被裁
+ 低清图片被强行放大
+ 同页过于拥挤
+ 跨页左右失衡

### 3.2 软评分
建议从以下维度综合评分：

+ 主体突出度
+ 留白舒适度
+ 章节完整性
+ 故事连贯性
+ 版式多样性
+ 风格统一度

### 3.3 全书级指标
+ 避免连续 3 页出现同构图
+ 避免连续多页密集拼图
+ 章节开头应有"起势页"
+ 章节结尾应有"收束页"

### 3.4 用户反馈闭环
支持将用户反馈回写为重排约束，例如：

+ "这张必须保留"
+ "这页不好看"
+ "不要跨页"
+ "主角换成某个人"

## 4. 关键算法建议
### 4.1 去重
推荐联合使用：

+ `感知哈希`
+ `embedding 相似度`
+ `连拍时间窗`

这样可以避免误删构图相似但表情略有变化的照片。

### 4.2 人物优先级
可通过以下因子计算人物权重：

+ 出现频次
+ 面部清晰度
+ 用户指定主角

目标是保证核心人物在全书中的曝光率。

### 4.3 标题与文案
可使用大模型基于章节标签生成短标题，例如：

+ `春日出游`
+ `夏末海边`
+ `生日小记`

但应限制标题长度和语气风格，确保统一性。

### 4.4 风格控制
风格层只建议控制：

+ 字体
+ 边距
+ 配色
+ 装饰密度
+ 文案语气

不要让风格层直接干扰底层几何布局。

### 4.5 局部重排
当用户替换一张图时，仅重算当前页和相邻页，避免全书重排带来的体验抖动。

## 5. 推荐数据结构
### 5.1 PhotoAsset
用于存储单张照片的源信息和分析结果：

+ 原图地址
+ 尺寸
+ EXIF
+ 质量分
+ 标签
+ 人物信息
+ embedding
+ 重复指纹

### 5.2 ChapterPlan
用于表达章节规划：

+ 章节标题
+ 起止照片
+ 页数预算
+ 风格 token
+ 摘要文案

### 5.3 PageLayout
用于表达单页布局：

+ 页面类型
+ 图片槽位
+ 裁切参数
+ 装饰参数
+ 文本块

---

> 修改开始：优化2（BookLayout 补全字段）
>

---

### 5.4 BookLayout
作为全书的唯一事实来源：

+ 书尺寸
+ 装订方式
+ 页面顺序
+ 章节结构
+ 全局风格
+ 导出参数
+ **version**: 排版版本号（每次重排或微调递增，从 1 开始），用于冻结下单时锁定版本
+ **status**: `draft`（可编辑）| `locked`（已冻结，不可再改）| `exported`（已导出 PDF）
+ **base_version**: 当前版本的父版本号，用于记录该版本由哪个版本演进而来，便于审计和回滚分析
+ **is_partial**: 是否为降级或未完全完成版本；若为 `true`，则禁止导出和下单
+ **score_snapshot**: 当前版本的评分快照，包含 `hard_violations`（硬规则违规列表）、`soft_scores`（软评分各维度得分）、`global_scores`（全书级指标得分）
+ **generation_meta**: 生成元数据，包含 `seed`（随机种子）、`pipeline_version`（流水线版本）、`model_versions`（各模型版本号）、`duration_ms`（生成耗时）、`photo_count`（有效照片数）、`input_hash`（本次生成输入摘要）
+ **render_snapshot**: 预览渲染快照，包含 `render_engine_version`、`font_pack_version`、`color_profile`、`thumbnail_profile`
+ **export_snapshot**: 导出快照，包含 `pdf_profile_version`、`bleed_mm`、`safe_margin_mm`、`font_embed_mode`、`image_sampling_policy`

**补充约束**：

+ `BookLayout` 是布局版本事实来源，但**不是**相册项目业务状态的唯一事实来源；项目是否可预览、可锁定、可下单应以 `Album.status` 为准
+ 一旦 `BookLayout.status = locked`，其 `pages`、`crop`、`text_blocks`、`render_snapshot`、`export_snapshot` 都必须冻结
+ 预览图与最终 PDF 必须绑定到同一个 `BookLayout.version` 以及同一份 `export_snapshot`

### 5.4.1 状态对象补充
为支撑 FastAPI + LangGraph 的工程实现，建议补充以下状态对象：

#### AlbumState
+ `album_id`
+ `status`: `draft | generating | reviewable | locked | ordered | archived`
+ `current_layout_version`
+ `latest_completed_task_id`
+ `allow_preview`
+ `allow_export`
+ `allow_order`

#### TaskState
+ `task_id`
+ `album_id`
+ `task_type`: `feature_extract | layout_generate | partial_regenerate | render_preview | export_pdf`
+ `status`: `queued | running | completed | failed | cancelled | timed_out | partial`
+ `idempotency_key`
+ `base_version`
+ `result_version`
+ `error_code`
+ `degrade_reasons`

#### UserOperation
+ `operation_id`
+ `album_id`
+ `base_version`
+ `op_type`
+ `payload`
+ `actor_id`
+ `created_at`

---

<<< 修改结束

---

### 5.5 RenderAsset
用于渲染相关输出：

+ 页面位图
+ 缩略图
+ 3D 纹理
+ 印刷源图映射

## 6. 系统架构设计
建议采用如下分层架构：

+ `前端应用`
+ `AI 编排服务`
+ `页面渲染服务`
+ `PDF 导出服务`
+ `订单与工厂服务`
+ `素材资产中心`

### 6.1 模块职责
#### 前端应用
负责：

+ 上传照片
+ 展示进度
+ 预览书样
+ 微调页面
+ 提交订单

前端不应承载重计算。

#### AI 编排服务
负责：

+ 基于 `FastAPI + LangGraph` 的任务入口、状态机编排和接口聚合
+ 特征提取
+ 照片清洗
+ 聚类分章
+ 页面规划
+ 版式求解
+ 文案生成
+ 全书评分

它应负责：

+ API 契约校验与幂等控制
+ LangGraph Checkpointer 持久化
+ 写接口的 `base_version` 冲突检查
+ 任务状态与相册状态的分离维护

#### 页面渲染服务
负责：

+ 页面位图
+ 缩略图
+ 预览图
+ 3D 纹理

应与排版引擎解耦。

#### PDF 导出服务
负责：

+ PDF/X 输出
+ 出血线
+ 色彩预检
+ 字体嵌入
+ 页码标记

#### 订单与工厂服务
负责：

+ SKU 与报价
+ 订单状态管理
+ 工厂路由
+ 生产状态回传
+ 物流信息同步

#### 素材资产中心
负责：

+ 原图
+ 缩略图
+ 特征文件
+ 排版中间结果
+ 渲染产物

它是全链路基础设施。

### 6.2 推荐架构图
```latex
[小程序/App/H5]
    |
    v
[API Gateway]
    |
    +--> [用户与订单服务]
    |
    +--> [素材资产服务]
    |        - 原图/缩略图/特征文件
    |
    +--> [AI 编排服务]
    |        - FastAPI API
    |        - LangGraph 状态机
    |        - 幂等/版本控制
    |        - 五层流水线编排
    |
    +--> [Python Worker]
    |        - 特征提取
    |        - 质量评估
    |        - 聚类分章
    |        - 版式求解
    |        - 文案生成
    |
    +--> [页面渲染服务]
    |        - 预览图
    |        - 3D 纹理
    |
    +--> [PDF 导出服务]
    |        - PDF/X
    |        - 出血/色彩检查
    |
    +--> [工厂对接服务]
             - 工厂路由
             - 生产状态
             - 物流回传
```

### 6.3 状态与写入边界
在主架构采用 `FastAPI + LangGraph` 的前提下，推荐遵循以下边界：

+ **FastAPI**：唯一对外写接口入口，负责鉴权、参数校验、幂等校验、版本冲突检测、返回任务 ID
+ **LangGraph**：负责任务流程、条件边、回退边、HITL 暂停恢复，不直接暴露给前端
+ **Python Worker**：执行模型推理、批处理、渲染触发、导出触发等重任务
+ **PostgreSQL**：持久化 `AlbumState`、`TaskState`、`BookLayout`、审计日志
+ **Redis**：缓存热点特征、任务锁、幂等键短期记录、流式进度临时状态

写入规则：

+ 前端不得直接写 `BookLayout JSON`
+ 所有用户编辑必须先转换为结构化操作，再由服务端应用到 `base_version`
+ 同一 `album_id` 同一时刻只允许一个全书级生成任务处于运行态
+ 局部重排与全书重排必须使用不同 `task_type`

## 7. MVP 技术选型建议
### 7.1 前端
+ 小程序优先可选 `UniApp` 或 `Taro`
+ 如果先做 H5 验证，也可选 `React` 或 `Next.js`

### 7.2 后端 API
`Python + FastAPI`

若 AI 侧以 Python 为主，推荐 `FastAPI` 作为核心编排服务，并承担：

+ REST / SSE 接口暴露
+ `idempotency_key` 校验
+ `base_version` 冲突检测
+ LangGraph 图执行入口
+ `TaskState` / `AlbumState` 查询接口

### 7.3 AI 与图像处理
+ **PyTorch** / **ONNX Runtime**：模型推理框架
+ **YOLOv8 / YOLOv11**：人脸检测 + 主体检测（COCO预训练），速度优势明显，300张照片检测可在1秒内完成
+ **FaceNet / ArcFace**：人脸特征提取与聚类（依赖YOLO提供的检测框作为输入）
+ **OpenCV / Pillow**：模糊度、过曝、闭眼等传统CV质量评估
+ **CLIP**：场景分类（零样本识别"海滩/生日/雪地"等场景）
+ **专用显著性模型**（如U2Net）：像素级显著性热力图，辅助智能裁切

常规模型推理和图像处理建议拆成异步任务，YOLO等轻量模型可部署为实时推理服务。

+ **LangGraph**：AI 编排层的状态机引擎，负责五层流水线的条件分支、循环重排、HITL 暂停恢复和流式进度推送。LangGraph 仅做编排，不执行模型推理。

### 7.4 队列与缓存
+ `Redis + Python Worker`
+ 可选 `Celery` / `Dramatiq` / `Arq`

用于上传后特征提取、排版任务、渲染任务。由于主后端选择为 `FastAPI + LangGraph`，建议一期优先使用 Python 原生任务栈，避免 `BullMQ` 带来的跨语言消息协议、状态回写和运维复杂度。

### 7.5 数据存储
+ `PostgreSQL` 存业务数据
+ 对象存储存原图和渲染结果
+ `Redis` 存热点缓存、分布式锁和流式进度

其中：

+ `PostgreSQL` 持久化 `albums`、`book_layouts`、`task_runs`、`user_operations`
+ `Redis` 不作为最终事实来源，只用于缓存、分布式锁和流式进度

### 7.6 3D 预览
+ Web 端可用 `Three.js`
+ 小程序端首期优先采用"伪 3D 翻页 + 页面位图"

不建议一期就做重型真 3D。

### 7.7 PDF 输出
建议优先选择服务端可控方案，先实现高精 PDF 生成，再逐步补齐专业印前检查与 PDF/X 能力。

---

> 新增开始：优化5（缓存策略）
>

---

### 7.8 缓存策略
为降低模型推理成本并满足性能目标，需要分层缓存策略：

| 缓存层级 | 缓存内容 | 存储位置 | TTL | 目的 |
| --- | --- | --- | --- | --- |
| 照片特征 | embedding 向量、人脸框、质量分、显著图 | PostgreSQL + Redis 热点 | 永久（关联照片生命周期） | 同一张照片只推理一次 |
| 场景标签 | CLIP / 分类器输出的场景分类结果 | Redis | 永久 | 场景标签不随照片变化 |
| 排版结果 | 完整的 BookLayout JSON | PostgreSQL | 订单完成后 30 天 | 支持用户历史查看和复购 |
| 页面缩略图 | 渲染位图（低分辨率，< 200KB/张） | 对象存储 + CDN | 7 天 | 加速预览加载 |
| 3D 纹理 | 预渲染翻页纹理集 | 对象存储 | 7 天 | 避免重复渲染 3D 翻页效果 |
| 模型权重 | PyTorch / ONNX 模型文件 | 内存常驻 | 服务生命周期 | 避免每次推理时加载模型 |


**推理热度缓存**（LRU）：最近处理的 N 张照片的特征向量常驻 Redis 内存，减少数据库查询和 GPU 冷启动开销。

**缓存失效策略**：

+ 用户删除或替换某张照片时，级联清除该照片的特征缓存和包含该照片的排版结果缓存
+ 模型版本升级时，批量标记旧版本特征为过期，异步重新提取
+ `BookLayout.version` 递增时，旧版缩略图不得作为新版预览复用
+ 字体包、导出参数、渲染引擎版本变化时，必须使 `render_snapshot` / `export_snapshot` 相关缓存失效

---

<<< 新增结束

---

## 8. 数据库设计建议
建议至少包含以下核心表：

### 8.1 users
+ 用户信息
+ 授权状态
+ 隐私同意记录

### 8.2 albums
+ 相册书项目
+ 场景模式
+ 开本
+ 风格
+ 当前状态
+ 当前布局版本
+ 是否允许预览/导出/下单

### 8.3 photos
+ 照片元数据
+ 源图地址
+ EXIF
+ 质量分

### 8.4 photo_features
+ embedding
+ 人脸结果
+ 主体框
+ 显著图
+ 标签

### 8.5 chapters
+ 章节顺序
+ 标题
+ 摘要
+ 风格 token

### 8.6 book_layouts
+ 当前版本布局 JSON
+ 评分
+ 是否锁定
+ 父版本号
+ 是否 partial
+ render/export 快照

### 8.7 task_runs
+ 任务类型
+ 幂等键
+ 基础版本号
+ 任务状态
+ 结果版本号
+ 降级原因
+ 错误码

### 8.8 user_operations
+ 操作类型
+ base_version
+ payload
+ actor
+ 执行结果

### 8.9 pages
+ 页面类型
+ 图片槽位
+ 文本块
+ 渲染结果

### 8.10 orders
+ 商品规格
+ 价格
+ 支付状态
+ 工厂状态

### 8.11 factories
+ 工厂能力
+ 装订方式
+ 纸张能力
+ 产能状态

### 8.12 audit_logs
+ 用户微调记录
+ 系统重排记录
+ 导出记录

## 9. 任务流设计
### 9.1 上传后
+ 立即生成缩略图
+ 异步提取特征
+ 写入资产中心

---

> 新增开始：优化3（特征预计算时序处理）
>

---

### 9.2 特征就绪检查
特征预计算与用户点击"生成"之间存在时序冲突：用户可能在特征尚未提取完毕时点击生成。需要明确的状态机设计：

```latex
                  ┌──────────────────┐
                  │   photos_uploaded │  照片上传完成
                  └────────┬─────────┘
                           │ 触发异步特征提取
                           v
                  ┌──────────────────┐
                  │ feature_extracting│  特征提取中（30-60s）
                  └────────┬─────────┘
                           │
              ┌────────────┴────────────┐
              │                         │
              v                         v
   ┌──────────────────────┐  ┌──────────────────────┐
   │ extraction_completed  │  │ extraction_partial    │
   │ 全部特征已就绪         │  │ 部分特征失败/超时      │
   └──────────┬───────────┘  └──────────┬───────────┘
              │                         │
              └────────────┬────────────┘
                           v
                  ┌──────────────────┐
                  │   ready_to_layout │  可触发排版
                  └──────────────────┘
```

**前端交互规则**：

| 状态 | "生成"按钮 | 提示文案 |
| --- | --- | --- |
| 特征提取中 | 显示进度% + 按钮置灰 | "AI 正在分析您的照片 (45/150) …" |
| 特征就绪 | 按钮可点击 | "AI 已就绪，点击开始排版" |
| 部分失败 | 按钮可点击 + 黄色提示 | "部分照片分析失败，可能影响排版效果，是否继续？" |
| 用户强制点击（特征未就绪） | 允许，但走慢速通道 | "特征尚在提取中，排版可能需要 60-90 秒" |


---

<<< 新增结束

---

### 9.3 用户点击生成
+ 若特征已就绪，只做聚类、规划和排版搜索
+ 尽量将核心流程压缩在 `20 秒` 目标内

### 9.4 用户预览
+ 先返回前几页位图
+ 剩余页面异步渲染

### 9.5 用户微调
+ 仅重算局部页面
+ 避免全书重排
+ 所有微调都必须带 `operation_id + base_version`
+ `换图` 默认只影响当前页和相邻页，`改文案` 不得触发几何布局重排
+ `指定主角人物` 视为全局偏好修改，至少回退到页面规划层重新评估

### 9.6 用户下单
+ 冻结布局版本
+ 确保预览和打印一致
+ 下单前必须校验 `Album.status = locked` 且 `BookLayout.is_partial = false`
+ PDF 导出必须绑定锁定版 `BookLayout.version`，禁止导出隐式最新版本

---

> 新增开始：优化4（端到端时序图）
>

---

### 9.7 端到端时序图
以下时序图覆盖从照片上传到预览的完整链路，标注了各阶段的同步/异步关系：

```latex
用户            前端              FastAPI         LangGraph/Worker   渲染服务          素材资产中心
 |               |                  |                |                |                |
 |--上传300张--> |                  |                |                |                |
 |               |--PUT 原图------->|--------------->|                |--存储原图----->|
 |               |                  |                |                |                |
 |               |<-返回 photo_ids--|                |                |                |
 |               |                  |                |                |                |
 |               |--POST 异步提特征->|                |                |                |
 |               |                  |--创建task------->|                |                |
 |               |                  |  + idempotency  |--特征提取(30s)-|                |
 |               |                  |                |--人脸/embedding|                |
 |               |                  |                |--质量分/标签   |                |
 |               |                  |                |--存特征文件---->|--存储--------->|
 |               |                  |<-任务完成通知---|                |                |
 |               |                  |                |                |                |
 |               |--轮询特征进度---->|                |                |                |
 |               |<-已就绪----------|                |                |                |
 |               |                  |                |                |                |
 |--点击生成---->|                  |                |                |                |
 |               |--POST layout---->|                |                |                |
 |               |                  |--校验base_version|                |                |
 |               |                  |--启动图执行------>|                |                |
 |               |<-task_id---------|                |                |                |
 |               |                  |                |--章节聚类(3s)--|                |
 |               |                  |                |--页面规划(5s)--|                |
 |               |                  |                |--版式生成(8s)--|                |
 |               |                  |                |--全书评分(2s)--|                |
 |               |                  |                |--存BookLayout->|--存储--------->|
 |               |                  |<--排版完成-------|                |                |
 |               |                  |                |                |                |
 |               |                  |--触发生成缩略图--------------->|                |
 |               |                  |                |                |--前5页位图     |
 |               |                  |                |                |--存CDN-------->|
 |               |                  |                |                |                |
 |               |--轮询排版状态---->|                |                |                |
 |               |<-completed-------|                |                |                |
 |               |  + 缩略图URL     |                |                |                |
 |               |                  |                |                |                |
 |--查看预览---->|                  |                |                |                |
 |               |<-前5页(秒开)------|<-CDN读取-------|<---------------|--返回位图------|
 |               |                  |                |--异步渲染剩余页--------------->|
 |               |--滑动翻页--------|                |  (用户浏览时    |--逐页渲染)     |
 |               |<-后续页(异步)-----|                |   后台完成)     |                |
```

**关键时间节点**：

| 阶段 | 预计耗时 | 说明 |
| --- | --- | --- |
| 照片上传 | 依赖网络 | 300 张压缩图约 30-60s |
| 特征提取 | 30-60s | 异步后台执行，用户无需等待 |
| 排版生成 | ≤20s | 特征就绪后触发，核心目标 |
| 前5页缩略图 | ≤3s | 排版完成后同步生成，优先交付 |
| 剩余页渲染 | 10-30s | 异步后台，用户浏览时逐步就绪 |


---

<<< 新增结束

---

## 10. 一期范围控制
建议 MVP 严格收敛：

+ 只支持一种开本，例如 `A4 正方形`
+ 只支持两种场景：`年度册`、`活动纪念册`
+ 只做 `4-6` 种高质量参数化版式
+ 只开放 4 类微调：`换图`、`交换`、`改文案`、`重裁切`
+ 工厂先接 `1-2` 家，先半自动流转

## 11. 关键风险
### 11.1 审美风险
算法能排"正确"，不一定排"惊艳"，需要评分器和人工兜底后台。

### 11.2 性能风险
如果所有模型都在线推理，很难满足 `100 张图 20 秒` 的目标。

### 11.3 稳定性风险
如果用户只改一张图就导致全书重排，体验会明显下降。

### 11.4 印刷风险
`RGB -> CMYK`、低清图放大、出血错误等问题，往往比页面美观问题更致命。

### 11.5 成本风险
3D 渲染和多模态理解都可能带来较高算力成本，MVP 必须做缓存和分层预计算。

## 12. 推荐落地顺序
1. 先定义 `BookLayout JSON` 和版式语法，作为全系统核心契约。
2. 实现 `照片清洗 + 聚类分章 + 固定版式填充`，**同步引入 LangGraph 作为流水线编排引擎**——LangGraph 是五层流水线的骨架，没有它后续的条件分支、循环重排和 HITL 都无法实现。此时仅走通线性流程，暂不上 HITL。
3. 引入评分器和 LangGraph 的条件边/循环边，实现"评分不合格 → 回退重排"的自动纠错。
4. 接入页面渲染与简化预览，此时在 LangGraph 中加入 HITL #2（全书预览确认）的 interrupt 暂停点。
5. 接入印刷 PDF 与工厂订单流，加入 HITL #4（下单最终确认）。
6. 最后再增强风格化、文案生成和真实 3D——这些是体验锦上添花，不阻塞核心闭环。

---

> 修改开始：优化6（调整优先事项顺序并追加第4项）
>

---

## 13. 当前最优先事项
如果项目马上进入研发，我建议最先完成以下四件事（按依赖关系排序）：

1. **定义版式模板 DSL** —— 它是排版引擎的"语言"，决定了哪些版式可被表达。没有 DSL，后续的 BookLayout 和评分函数都无法开始。DSL 应至少描述：槽位数量、槽位几何约束、裁切规则、装饰参数范围。
2. **基于 DSL 定义 BookLayout JSON 字段规范** —— 全书布局的唯一事实来源，是所有服务的核心数据契约（详见 5.4 节）。
3. **定义排版评分函数** —— 基于 BookLayout 的结构，明确硬规则的检测逻辑和软评分的权重公式。这是排版质量的最后防线。
4. **跑通最短端到端 Demo** —— 用 1 张照片 + 1 页 + 1 种版式（单图满版） + 输出 1 张缩略图，验证整条流水线是通的，再逐步加复杂性。

---

<<< 修改结束
