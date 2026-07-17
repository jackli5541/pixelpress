# 阶段 B：照片清洗 V2.1 说明

**文档版本**：v2.1
**分析版本**：`b2-local-v3`
**技术策略**：`technical-v3`
**决策策略**：`cleaning-policy-v3`
**更新时间**：2026-07-17

## 1. 处理流程

```text
ContentProfileExtractor
-> TechnicalFeatureExtractor
-> FaceFeatureExtractor
-> DuplicateGrouper
-> CleaningDecisionPolicy
-> ReviewQueueBuilder
-> 保留/已移除双照片池
```

固定原则：

- 全部算法在 Worker 内离线运行，不调用外部视觉服务。
- 不物理删除原图，不做人脸身份识别。
- 用户决定和 `user_delegated` 决定在重跑后保持不变。
- 只有精确重复和校准后的不可恢复模糊可以自动移出。
- 无法可靠判断时默认保留，不因为模型失败制造复核项。
- 曝光、普通分辨率、低纹理和一般清晰度只作为信息提示。

决策优先级：

```text
user / user_delegated
> unrecoverable_blur
> exact_duplicate
> duplicate preferred
> reliable face review
> keep
```

## 2. 内容类型与曝光

### 2.1 ContentProfileExtractor

每张图片在技术分析前输出：

```text
capture_kind: camera_photo | screenshot_or_graphic | unknown
visual_domain: photographic | illustration | mixed | unknown
confidence
signals
```

截图识别综合以下信号：

- 截图文件名模式，包括中英文和日文常见命名。
- PNG 容器与相机 EXIF 信息。
- 平坦色块比例。
- 水平/垂直边缘集中度。
- 量化颜色变化比例。

PNG 不能单独决定图片是截图。相机 EXIF 是摄影照片的强信号；无 EXIF 的插画和截图使用视觉统计判断。

### 2.2 曝光分析

高置信截图或插画返回：

```json
{
  "score": null,
  "severity": "not_applicable",
  "applicable": false
}
```

前端显示 `-- / 不适用`，不生成曝光问题，也不进入复核。

摄影照片使用 8x8 分块曝光分析，结合：

- `p01/p05/p50/p95/p99` 亮度分位数。
- 阴影和高光裁切比例。
- 有信息分块比例。
- 大面积局部信息丢失。
- 有效动态范围。

只有大面积裁切且局部信息明显丢失时才产生曝光警告，避免夜景、高调照片和局部强光误报。

## 3. 清晰度与严重模糊底线

清晰度不再由单个 Laplacian 值决定。`TechnicalFeatureExtractor` 在长边 1024 和 512 两个尺度提取：

- Laplacian variance。
- Tenengrad。
- 8x8 分块清晰度 `p10/p50/p90`。
- 边缘密度和熵。
- 有效纹理分块比例。
- 梯度方向直方图和运动模糊方向集中度。
- 1024、512 输出尺度的细节可辨识度。

`sharpness_warning` 只表示风险。只有同时满足下列条件才产生 `sharpness_severe`：

```text
有效纹理充分
AND 最清楚的有效分块仍不可辨识
AND 1024 尺度低于底线
AND 512 尺度低于底线
AND 运动模糊或全方向失焦证据成立
```

低纹理不足时返回 `sharpness_undetermined`，不得自动移出。人物照片还要求主要人脸区域同样达到严重模糊底线。

自动移出字段：

```text
hard_reject=true
hard_reject_reason=unrecoverable_blur
auto_exclusion_source=system_unrecoverable_blur
```

`quality_score` 仅用于展示和组内排序，不直接决定自动移出或人工复核。截图/插画不计算曝光权重，低纹理使用中性清晰度分。

## 4. 人脸与人物分析

### 4.1 真人照片

真人路径使用 `mediapipe==0.10.35`：

- BlazeFace full-range：人脸数量、位置和 6 个关键点。
- Face Landmarker：姿态、闭眼和表情 blendshape。
- Pose Landmarker：实验性身体裁切，默认关闭。

处理限制：

- 整图最长边 1600 检测。
- 大图检测为空或只有小脸时进行有限分块补检。
- 脸部短边至少 64px 才分析脸部清晰度。
- 脸部扩边、对齐到 192x192 后计算清晰度。
- 短边至少 96px、检测可靠时才判断闭眼和高价值风险。
- 表情只在同一重复/连拍组中判断离群，不做全局异常表情分类。

### 4.2 动漫与插画

截图、插画或真人检测为空时，使用 `anime-face_yolov3.onnx`。模型来源为 hysts Anime Face Detector 的 MIT 模型和 ailia ONNX 转换，运行时通过 OpenCV DNN CPU 推理。

参数：

```text
input=608x608
confidence=0.70
nms=0.40
```

模型原始 ONNX 的内置后处理与 OpenCV DNN 存在类型兼容问题。镜像构建阶段会校验源模型 SHA-256，并裁剪为 decoded boxes、class confidence 和 objectness 三路输出；Worker 在代码中计算合成置信度和 NMS。

动漫路径只输出：

- 人脸数量和框。
- 检测来源。
- 边缘裁切风险。
- 脸部清晰度。

动漫不执行 blendshape，不判断闭眼、表情或遮挡。未检测到动漫脸时默认保留，不宣称图片一定无人。加载或推理失败只写入诊断字段，不中断整张照片分析。

### 4.3 数据最小化

系统不保存：

- 人脸 embedding。
- 完整 478 点人脸关键点。
- 完整姿态点。
- 分割掩码。

## 5. 重复分组与组内首选

精确重复使用文件内容 SHA-256；相似照片和连拍使用 pHash、颜色直方图、长宽比和拍摄时间进行完整链接聚类，避免传递式误合并。

组内首选顺序：

```text
未命中硬底线
-> 人脸集合完整度
-> 低分位人脸清晰度
-> 闭眼/遮挡/裁切风险
-> 全图技术质量
-> 分辨率
-> 稳定排序字段
```

精确副本可自动移出；相似/连拍组进入组级复核。人脸风险不会直接自动移出。

## 6. 复核队列与决定

复核项分为：

- `single_photo`：高可靠人物风险。
- `duplicate_group`：相似照片或连拍组。

同一照片只能出现在一个复核项中，重复组吸收成员的模糊、人脸和裁切原因。

以下情况不再进入复核：

- 曝光提示。
- 普通分辨率提示。
- 低纹理和一般清晰度提示。
- 人脸模型不可用或分析失败。
- 低置信人脸、遮挡和表情结果。
- 无法可靠判断的截图、插画和动漫图片。

### 6.1 单项处理

`POST /albums/{id}/clean/review/resolve`

单图支持 `keep/remove`；重复组支持 `accept_preferred/keep_all`。接口使用 `expected_content_revision` 防止旧页面覆盖新决定。

### 6.2 剩余全部交给系统

`POST /albums/{id}/clean/review/resolve-remaining`

```json
{
  "expected_content_revision": 123
}
```

该接口在一个事务内处理当前项及剩余全部复核项：

- 单图按系统建议处理，不确定时保留。
- 高置信相似组采用系统首选，否则全部保留。
- 不覆盖已有用户决定。
- 全批只增加一次 `content_revision`。
- 所有新决定写入 `decision_source=user_delegated`。
- 无待复核项时幂等成功，旧 revision 返回 409。

响应包含：

```text
resolved_review_count
changed_items
summary
content_revision
remaining_review_count
```

## 7. 前端行为

任务成功且存在待复核项时，页面按 `review_session_id` 自动打开一次复核弹窗。

- 单图提供保留、移除、剩余全部交给系统。
- 重复组提供采用首选、全部保留、剩余全部交给系统。
- “剩余全部交给系统”明确包含当前项，只调用一次批量 API。
- 弹窗标题和操作区固定，内容区内部滚动。

最终页面只展示两个照片池：

```text
保留照片：decision != remove
已移除：decision == remove
```

照片池行为：

- 高度 `clamp(480px, 68vh, 760px)`，内部滚动。
- 每次渲染 24 张，滚动追加 24 张。
- IntersectionObserver 根节点为照片池容器。
- 切换照片池或方向筛选时重置滚动位置。
- 保留照片可立即移除，已移除照片可立即恢复。
- 本地乐观更新位置和计数，只锁定当前照片按钮。
- 请求失败回滚，成功后使用增量响应校准，不全量刷新页面。

## 8. 上传分批、限流与重试

前端上传规则：

```text
每批最多 50 张
每批最多 160 MiB
最多 2 个并发批次
```

上传接口限流键为认证用户和相册组合，默认 `120/minute`，不再只按 IP。429 响应包含：

```text
Retry-After
X-RateLimit-Limit
X-RateLimit-Remaining
X-RateLimit-Reset
```

前端按 `Retry-After` 自动重试最多 3 次；缺少响应头时使用 1、2、4 秒退避。重试期间不增加已完成进度，最终失败才计入失败批次。

## 9. 模型交付

模型运行时禁止下载。生产镜像采用独立模型构建阶段：

1. 下载源 ONNX。
2. 校验源文件大小和 SHA-256。
3. 裁剪为 OpenCV DNN 兼容输出。
4. 校验生成模型 SHA-256。
5. 复制到最终 Worker 镜像。

模型文件不直接提交 Git，避免超过 GitHub 单文件限制。来源、许可证、源哈希、准备方式和运行哈希记录在 `backend/models/cleaning/manifest.json`。

Linux 镜像必须安装 `libgl1`，否则 OpenCV 和 MediaPipe 无法加载。

## 10. API 摘要

| 方法 | 路径 | 用途 |
|---|---|---|
| `POST` | `/albums/{id}/clean` | 创建清洗任务 |
| `GET` | `/albums/{id}/clean/results` | 获取双池摘要、复核队列、重复组和照片结果 |
| `PATCH` | `/albums/{id}/clean/decisions` | 手动移除或恢复照片 |
| `POST` | `/albums/{id}/clean/review/resolve` | 原子处理单图或重复组 |
| `POST` | `/albums/{id}/clean/review/resolve-remaining` | 一次处理当前及剩余复核项 |
| `POST` | `/albums/{id}/clean/reset` | 重置系统分析，保留用户决定 |

接口继续使用统一响应包：

```json
{
  "code": 0,
  "message": "ok",
  "request_id": "...",
  "data": {}
}
```

## 11. 测试与本地验收

直接相关测试覆盖：

- 多尺度模糊、运动模糊、低纹理和缩放一致性。
- 截图曝光不适用和技术提示默认保留。
- 硬底线优先级、缓存一致性和决定重跑保持。
- 动漫原始输出置信度、NMS 和能力边界。
- 复核队列去重、批量系统决策、幂等性和 revision 冲突。
- 上传限流隔离、标准响应头和前端退避。
- 弹窗批量决策、固定滚动区、双池实时移动和失败回滚。

2026-07-17 使用本地存储中的 478 张混合集进行离线实跑：

| 指标 | 结果 |
|---|---:|
| 分析成功 | 478 / 478 |
| 曝光问题 | 0 |
| 曝光不适用 | 314 |
| 动漫脸 | 95 |
| 真人脸 | 97 |
| 严重模糊硬删除 | 0 |
| 精确重复自动移出 | 83 |
| 复核项 | 3 |
| 复核率 | 0.63% |

该数据集用于回归当前误报和复核量，不替代带人工真值的动漫人脸精确率/召回率标注集，也不替代严重模糊发布门槛评测。

## 12. 发布门槛与边界

严重模糊自动移出仍需满足：

- 自动移出精确率至少 99.5%。
- 必须保留误移出率的 95% Wilson 上界不超过 0.5%。
- 低纹理必保集零硬删除。
- 同源缩放样本判定一致率至少 99%。

动漫脸标注集目标：

- 短边至少 64px 的人脸精确率至少 95%。
- 召回率至少 90%。
- 纯 UI 截图误检率不超过 1%。

当前明确不做：

- 人脸身份识别。
- 物理删除原始照片。
- 动漫闭眼、表情和遮挡判断。
- 低置信模型结果自动移出。
- 运行时在线下载模型。
