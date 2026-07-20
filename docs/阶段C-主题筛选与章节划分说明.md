# 阶段 C：主题筛选与章节划分

## 1. 阶段边界

阶段 C 位于照片清理之后、版面规划之前，前端工作流顺序保持：

`upload -> cleaning -> chapters -> planning -> export`

`chapters` 阶段内部顺序为：

`主题分析 -> 选择主题 -> 跨模态相关性评分 -> 人工复核 -> 确认主题快照 -> 章节聚类 -> 章节命名与持久化`

入口 API 保持统一响应包 `{ code, message, request_id, data }`：

- `POST /albums/{album_id}/theme-analysis`
- `GET /albums/{album_id}/theme-workspace`
- `POST /albums/{album_id}/theme-selection`
- `PATCH /albums/{album_id}/theme-review/decisions`
- `POST /albums/{album_id}/theme-review/confirm`
- `POST /albums/{album_id}/theme-review/reopen`
- `POST /albums/{album_id}/cluster`

耗时操作只在 API 层创建任务。ARQ handler 获取相册工作流锁后，分别调用 `ThemeCurationService.execute_analysis`、`ThemeCurationService.execute_selection` 和 `ChapterService.execute_cluster_chapters`。API 不承载算法和持久化业务。

## 2. 主题分析与状态

主题 profile 的持久状态为：

- `candidates_ready`：候选主题已生成，等待用户选择。
- `review_pending`：照片已完成评分，等待处理所有 `review`。
- `confirmed`：主题及照片范围已经确认，并绑定 `confirmed_revision`。
- `superseded`：被后续主题 profile 替代。

前端工作区据此映射为 `needs_analysis`、`choose_theme`、`review_theme_photos`、`ready_to_cluster`。

主题分析只读取清理后保留的照片。`ChapterFeatureService` 提取并缓存照片 embedding 与语义特征，再由代表图和特征摘要生成 3 类入口：系统主题候选、自定义主题候选和固定的“完整记录”。LLM 可以生成候选标题、概念与结构化约束，但不能决定任何照片的去留。

“完整记录”是显式旁路：所有清理后照片直接建议保留，不经过主题 embedding 或标定。

## 3. 照片特征缓存

`PhotoChapterFeature` 是主题筛选与章节聚类共用的唯一照片向量缓存，不创建第二套主题向量。缓存命中键包含：

`photo_id + content_sha256 + feature_version + embedding_model + embedding_dimension + semantic_model`

单批照片并行执行两类提取：

- multimodal embedding provider 生成照片向量；默认配置为 DashScope `qwen3-vl-embedding`、512 维。
- 章节语义模型生成 `scenes`、`activities`、`setting`、`capture_type`。

照片内容从 `file_store` 存储抽象读取。embedding、语义特征允许部分成功；缓存记录 `success / partial / failed` 和错误原因。章节可以在部分特征缺失时降级，主题筛选则在照片向量缺失或版本不一致时强制进入人工复核。

## 4. 跨模态主题查询

主题文本查询由三组证据构成：

1. `raw`：用户原始主题或选中候选标题，是主信号。
2. `expanded`：以“照片主要视觉内容直接表现该主题”为锚点的严格扩展描述，是辅助信号。
3. `negative`：用户或候选中显式给出的排除概念。

候选中的 include、活动、地点、人物等概念先经过严格语义蕴含判断。只有被原始主题直接蕴含的概念进入 expanded 描述；未被蕴含的概念直接丢弃，不转成 negative。只有显式排除描述生成 negative embedding。

主题文本与照片必须使用同一个 multimodal embedding provider、model 和 dimension。查询向量版本为 `cross-modal-query-v2-anchored`。

对照片向量 `p`，计算：

```text
raw      = cosine(p, raw_query)
expanded = mean(cosine(p, expansion_query_i))
positive = 0.7 * raw + 0.3 * expanded
negative = max(cosine(p, negative_query_i))
margin   = positive - negative
penalty  = 0.5 * max(0, negative - positive)
signal   = positive - penalty
```

没有扩展描述时 `expanded = raw`；没有 negative 时不施加惩罚。这里不存在 `max(raw, expansion)`、相册 percentile、Top-K、主题名称命中、scene/activity 标签加分或逐照片 VLM 核验。

## 5. 标定与去留决策

评分版本为 `cross-modal-relevance-v3-embedding-only`。标定 artifact 必须同时满足：

- 至少 500 个主题-照片对。
- 至少 8 类主题。
- 每条样本至少两名独立标注者。
- 候选 precision 不低于 0.90。
- 相关照片 recall 不低于 0.70。
- 误移出率不高于 0.02。
- provider、model、dimension、query version、scoring version 与运行时完全一致。

标定先对 `raw / expanded / negative / margin` 训练标准化逻辑回归，再用单调分段映射得到相关概率。只有 artifact 自身 `enabled: true`、数据门槛和质量门槛均通过、版本完全匹配时，工作区状态才是 `ready`，自动决策才启用。

标定状态及行为：

- `ready`：概率大于等于 keep 阈值为 `keep`，小于等于 exclude 阈值为 `exclude`，中间为 `review`。
- `missing / disabled / mismatch`：所有照片均为 `review`，只按归一化 embedding signal 排序，前端显示“相似度排序”而非百分比。

用户显式输入的年份或日期是独立约束。缺少拍摄时间时进入 `review`；超出范围只有在标定可自动决策时才能移出，未标定时仍为 `review`。模型推断的地点、活动和人物不会直接移出照片。

最终决策始终是 `user_decision ?? suggested_decision`。三个集合 `keep / review / exclude` 互斥；存在任何 `review` 时禁止确认。用户可批量保留或移出，也可恢复自动移出的照片，不会在确认时把未决照片静默改成 `exclude`。

## 6. 章节启动条件

章节任务创建和 worker 执行时都会重新检查：

- 清理阶段没有待复核照片。
- 存在与当前 `album.theme_input_revision` 一致的 confirmed theme profile。
- 主题 assessment 中没有 `review`。
- 仅把清理后有效且主题最终决策不为 `exclude` 的照片交给聚类。

任务幂等键包含相册、`content_revision` 和 pipeline version。worker 开始和重建前检查任务 revision/取消状态，过期任务以 `stale_task` 失败，不覆盖新结果。

## 7. 语义层级聚类 `c5-activity-continuity-v1`

### 7.1 相邻照片连续性

有拍摄时间的照片先按 `taken_at` 和稳定 ID 排序。每对相邻照片计算可用证据的加权平均；缺失证据从分母中移除：

| 证据 | 权重 | 说明 |
| --- | ---: | --- |
| embedding | 0.45 | cosine 经区间归一化 |
| time | 0.20 | 拍摄时间接近度 |
| GPS | 0.15 | 经纬度距离接近度 |
| semantic | 0.10 | scene/activity/setting 的 Jaccard 相似度 |
| capture type | 0.05 | 拍摄类型是否一致 |
| histogram | 0.05 | 清理阶段颜色直方图相似度 |

按相邻照片时间差使用不同的 segment 连续性阈值：

- 不超过 15 分钟：`0.32`
- 不超过 2 小时：`0.42`
- 不超过 6 小时：`0.50`
- 更长或缺少时间差：`0.58`

连续性分数低于阈值时切分 segment。显式主题年份跨年、短时间内活动集合完全变化也会形成 segment 边界。主题标题本身不参与相似度加权。

### 7.2 segment 合并为 chapter

segment 形成后，再按更宽的叙事边界合并为 chapter：

- 对 `activity_first`，一分钟内的连续拍摄若连续性分数通过、拍摄类型一致，并有足够的语义、色彩或 embedding 连续证据，则优先归入同一活动 chapter；标签波动只保留为内部 segment。
- 其他策略下，相邻 segment 间隔不超过 6 小时，默认保持同一 chapter。
- 间隔超过 30 天，强制切分。
- GPS 距离超过 300 km 且时间差超过 30 分钟，切分。
- 间隔超过 72 小时且 embedding cosine 低于 0.75，切分。
- 间隔超过 24 小时且 embedding cosine 低于 0.55，切分。
- 间隔超过 12 小时、拍摄类型变化且 cosine 低于 0.65，切分。

`activity_first` 会按活动、内容或拍摄类型变化切章，但不会因连续拍摄中不稳定的细粒度标签而重复拆章；`location_first` 会更积极地按 50 km 以上的位置变化切章；`time_first` 和 `balanced` 当前沿用通用 chapter 边界，显式年份仍在 segment 层强制分开。

### 7.3 无拍摄时间照片

无时间照片不参与时间排序。算法将其 embedding 与各 segment 成员比较，只有最佳相似度不低于 `0.78`，且比第二名至少高 `0.08`，才分配到最佳 segment。否则进入独立的“待确认照片”chapter，并标记 `weak_assignment` 和低置信度。

segment 与 chapter 都保存置信度、是否需要复核、边界证据、特征覆盖率、代表照片、降级照片数和原因统计。embedding 覆盖率低于 0.8 时，置信度上限为 0.55。

## 8. 无 embedding 降级 `c1-events-v1`

若整批保留照片没有任何可用 embedding，`ChapterService` 明确回退到 legacy 算法，而不是伪造语义结果。该算法使用：

`time 0.55 + GPS 0.25 + scene 0.15 + histogram 0.05`

边界阈值为 `0.45`；30 天以上强制切章，2 小时内且未跨越 300 km 保持连续。无时间照片按 GPS/scene/histogram 分配，最佳分数至少 `0.60` 且领先第二名 `0.15`，否则进入待确认 chapter。

该 fallback 是 provider 不可用、配置缺失或照片特征提取失败时的正式可恢复路径，不能作为冗余代码删除。

## 9. 命名、持久化与重建

确定性聚类先生成规则名称和摘要。AI 命名启用时，只向模型提供固定 chapter 的代表图、时间范围、有限场景标签、圆整 GPS 和主题上下文；模型只能返回同一 `chapter_key` 的名称与描述，不能修改照片归属。命名失败保留规则名称。

聚类结果通过 `ChapterRepository` 一次写入 chapter、segment 和有序照片关系，同时保存算法版本、置信度和 explanation。完成后相册进入 `CLUSTERED`，`content_revision` 增加，任务记录结果 revision、指标与 debug 信息。

更换主题或重新打开已有章节的主题复核时，必须显式 `confirm_rebuild`。确认后清除旧章节、页面和渲染产物，将相册退回 `CLEANED`，并增加 revision，使旧 ARQ 任务失效。普通章节重建同样需要确认。

## 10. 代码职责

- `modules/theme/api.py`、`modules/chapter/api.py`：鉴权、参数、HTTP 错误与统一响应。
- `jobs/handlers.py`：ARQ task claim、工作流锁和 Service 调用。
- `services/theme_curation_service.py`：主题任务编排、状态、用户决策和 Repository。
- `engines/theme_pipeline.py`：候选生成、约束规范化、严格概念蕴含。
- `engines/theme_relevance_engine.py`：纯 embedding 查询、评分、标定与决策。
- `services/chapter_feature_service.py`：共用照片特征提取与缓存。
- `engines/chapter_engine/semantic_service.py`：`c5` 活动连续性层级聚类。
- `engines/chapter_engine/service.py`：模式选择与 `c1` fallback。
- `engines/chapter_engine/prompt_pipeline.py`：固定章节的可选命名。
- Repository：profile、assessment、decision event、feature、chapter 和 segment 持久化。
- `storage/file_store.py`：照片与派生产物的存储边界。

## 11. 验收

```powershell
start.bat test
start.bat test-render
start.bat ps
cd frontend
npm run build
cd ..\backend
python scripts/evaluate_theme_relevance.py <manifest> --dataset-version <version> --output <calibration.json>
```

阶段 C 的定向回归至少覆盖：主题相关性 Engine、主题 Service/API、语义章节、legacy fallback、revision/ARQ 恢复和前端三集合互斥行为。
