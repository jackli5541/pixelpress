# 版式模板 DSL 规范

> 版本：v1.0 | 状态：draft | 关联：AI自动排版系统设计方案-v2.md 第 2.2、2.5、13 节

## 1. 设计原则

1. **声明式**：描述"这个版式是什么样"，而非"如何画出来"——由排版引擎负责渲染
2. **参数化**：同一版式适配横图/竖图/方图，不硬编码坐标
3. **印刷安全优先**：所有版式必须定义出血线（3mm）和安全裁切区，确保人脸和主体不被切掉
4. **层级约束**：槽位之间可以有优先级和排他关系
5. **版本可追踪**：每个版式模板有版本号，变更可追溯

---

## 2. 坐标系与单位

### 2.1 页面模型

```
┌─────────────────────────────┐
│         出血区 (bleed)       │  ← 内容延伸至此，超出裁切线的部分会被裁掉
│   ┌─────────────────────┐   │
│   │    安全区 (safe)     │   │  ← 重要内容（人脸、文字）必须在此区域内
│   │   ┌─────────────┐   │   │
│   │   │  核心区      │   │   │  ← 主体的视觉焦点区域
│   │   │  (core)     │   │   │
│   │   └─────────────┘   │   │
│   └─────────────────────┘   │
└─────────────────────────────┘
```

- **裁切区（trim）**：物理页面裁切后的最终尺寸，坐标系以此为准
- **出血区（bleed）**：裁切区外扩 3mm，背景和图片需延伸至此，防止裁切误差露白
- **安全区（safe）**：裁切区内缩 5mm，人脸、文字等重要内容必须在此区域内
- **核心区（core）**：安全区内缩 10%，主体视觉焦点的最佳位置

### 2.2 坐标表达

以下三种表达方式等效，可混用：

| 方式 | 示例 | 说明 |
|------|------|------|
| 百分比 | `x: 50%`, `w: 100%` | 相对裁切区宽/高，推荐 |
| 毫米 | `x: 105mm` | 绝对物理尺寸，用于固定边距 |
| 比例 | `aspect: 16:9` | 图槽宽高比约束 |

### 2.3 默认值

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `page` | `single` | 单页或跨页 |
| `bleed` | `3mm` | 出血宽度 |
| `safe_margin` | `5mm` | 安全区内缩 |
| `unit` | `percent` | 坐标单位 |

---

## 3. DSL 语法（YAML）

### 3.1 顶层结构

```yaml
version: "1.0"
templates:
  single_full_bleed:
    meta:
      name: "单图满版"
      category: "single_page"
      page: single          # single | spread（跨页）
      orientation: any      # landscape | portrait | square | any
      description: "整页铺满一张照片，适合展示高画质大场景"
    slots:
      - id: main
        type: photo
        geometry:
          x: 0%
          y: 0%
          w: 100%
          h: 100%
        crop: auto_best     # 裁切模式，详见第5章
        bleed: true         # 是否延伸至出血区
    text:
      - id: page_number
        type: page_number
        position: bottom_center
    decoration:
      mode: none            # none | minimal | moderate | rich
  # ... 更多版式
```

### 3.2 字段速查表

#### meta（版式元信息）

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `name` | string | 是 | 版式中英文名 |
| `category` | string | 是 | `single_page` / `spread` / `chapter_cover` / `chapter_end` |
| `page` | enum | 是 | `single`（单页）或 `spread`（跨页对开） |
| `orientation` | enum | 是 | `landscape` / `portrait` / `square` / `any` |
| `description` | string | 否 | 版式说明 |

#### slot（槽位）

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | string | 是 | 槽位唯一标识 |
| `type` | enum | 是 | `photo` / `decoration` / `placeholder` |
| `geometry` | object | 是 | 位置和尺寸 |
| `crop` | enum | 否（默认 auto_best） | 裁切模式 |
| `bleed` | bool | 否（默认 true） | 是否延伸至出血区 |
| `priority` | int | 否（默认 0） | 槽位优先级，数字越大越优先。排版引擎优先填充高优先级槽位 |
| `optional` | bool | 否（默认 false） | 照片不足时此槽位可留空 |
| `constraints` | object | 否 | 此槽位的特殊约束 |

#### geometry（几何）

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `x` | value | 是 | 左上角 X 坐标（% 或 mm） |
| `y` | value | 是 | 左上角 Y 坐标 |
| `w` | value | 是 | 宽度 |
| `h` | value | 是 | 高度 |
| `margin` | value | 否 | 槽位之间的间距 |

#### text（文本块）

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | string | 是 | 文本块标识 |
| `type` | enum | 是 | `title` / `subtitle` / `body` / `page_number` / `caption` |
| `position` | enum 或 object | 是 | 预设位置（如 `bottom_center`）或具体坐标 |
| `style` | object | 否 | 字体/字号/颜色/对齐 |

---

## 4. MVP 版式模板库（6 种）

### 4.1 单图满版（single_full_bleed）

**适用**：高画质大场景照片、封面图、章节起势页

```yaml
single_full_bleed:
  meta:
    name: "单图满版"
    category: single_page
    page: single
    orientation: any
    min_photo_quality: 0.6   # 此版式要求照片质量分 ≥ 0.6
  slots:
    - id: main
      type: photo
      geometry: { x: 0%, y: 0%, w: 100%, h: 100% }
      crop: auto_best
      bleed: true
  text:
    - id: page_number
      type: page_number
      position: bottom_right
      style: { font_size: 10pt, color: "#ffffff88" }
  decoration:
    mode: none
```

### 4.2 双图对开（double_side_by_side）

**适用**：横图对比、前后对比、双人合照

```yaml
double_side_by_side:
  meta:
    name: "双图对开"
    category: single_page
    page: single
    orientation: portrait
    description: "两张竖图上下或左右排列，适合对比叙事"
  slots:
    - id: left
      type: photo
      geometry: { x: 3%, y: 3%, w: 45.5%, h: 94% }
      crop: auto_best
      margin: 3%
    - id: right
      type: photo
      geometry: { x: 51.5%, y: 3%, w: 45.5%, h: 94% }
      crop: auto_best
  text:
    - id: page_number
      type: page_number
      position: bottom_center
  decoration:
    mode: minimal
    divider: true           # 中缝装饰线
```

### 4.3 三图叙事（triple_narrative）

**适用**：活动故事线，一张主图 + 两张辅图

```yaml
triple_narrative:
  meta:
    name: "三图叙事"
    category: single_page
    page: single
    orientation: any
    description: "一大两小，主图占视觉重心，辅图补充细节"
  slots:
    - id: hero
      type: photo
      geometry: { x: 3%, y: 3%, w: 94%, h: 60% }
      crop: auto_best
      priority: 1             # 高优先级，优先分配最好照片
      constraints:
        prefer_subject: true  # 优先选择有清晰主体的照片
    - id: sub_left
      type: photo
      geometry: { x: 3%, y: 66%, w: 45.5%, h: 31% }
      crop: auto_best
      optional: true
    - id: sub_right
      type: photo
      geometry: { x: 51.5%, y: 66%, w: 45.5%, h: 31% }
      crop: auto_best
      optional: true
  text:
    - id: page_number
      type: page_number
      position: bottom_right
  decoration:
    mode: minimal
    gap: 3%
```

### 4.4 九宫格摘要（grid_nine）

**适用**：活动精彩瞬间汇总、合影集锦

```yaml
grid_nine:
  meta:
    name: "九宫格摘要"
    category: single_page
    page: single
    orientation: any
    min_photos: 4             # 最少需要 4 张照片
    max_photos: 9             # 最多 9 张
    description: "3×3 网格排列，适合活动瞬间汇总"
  slots:
    - id: g1
      type: photo
      geometry: { x: 3%, y: 3%, w: 30%, h: 30% }
      crop: center_face        # 优先裁切到人脸居中
    - id: g2
      type: photo
      geometry: { x: 35%, y: 3%, w: 30%, h: 30% }
      crop: center_face
    - id: g3
      type: photo
      geometry: { x: 67%, y: 3%, w: 30%, h: 30% }
      crop: center_face
    - id: g4
      type: photo
      geometry: { x: 3%, y: 35%, w: 30%, h: 30% }
      crop: center_face
    - id: g5
      type: photo
      geometry: { x: 35%, y: 35%, w: 30%, h: 30% }
      crop: center_face
    - id: g6
      type: photo
      geometry: { x: 67%, y: 35%, w: 30%, h: 30% }
      crop: center_face
    - id: g7
      type: photo
      geometry: { x: 3%, y: 67%, w: 30%, h: 30% }
      crop: center_face
      optional: true
    - id: g8
      type: photo
      geometry: { x: 35%, y: 67%, w: 30%, h: 30% }
      crop: center_face
      optional: true
    - id: g9
      type: photo
      geometry: { x: 67%, y: 67%, w: 30%, h: 30% }
      crop: center_face
      optional: true
  text: []
  decoration:
    mode: minimal
    gap: 2%
    border: { width: 0.5pt, color: "#cccccc" }
```

### 4.5 章节扉页（chapter_cover）

**适用**：章节开头，大幅标题 + 单张背景图

```yaml
chapter_cover:
  meta:
    name: "章节扉页"
    category: chapter_cover
    page: single
    orientation: any
    description: "章节封面：满版背景图 + 半透明遮罩 + 章节标题"
  slots:
    - id: background
      type: photo
      geometry: { x: 0%, y: 0%, w: 100%, h: 100% }
      crop: auto_best
      bleed: true
      constraints:
        prefer_landscape: true   # 优先选横图
  text:
    - id: chapter_title
      type: title
      position: center
      style:
        font_size: 28pt
        color: "#ffffff"
        align: center
        weight: bold
  decoration:
    mode: moderate
    overlay: { color: "#000000", opacity: 0.3 }   # 半透明遮罩，使文字可读
```

### 4.6 跨页满版（spread_full_bleed）

**适用**：全景照片、大合影、风景横图

```yaml
spread_full_bleed:
  meta:
    name: "跨页满版"
    category: spread
    page: spread              # 跨页（左右两页合并为一张大图）
    orientation: landscape
    min_photo_quality: 0.7
    description: "一张照片横跨左右两页，适合全景图和横幅合影"
  slots:
    - id: main
      type: photo
      geometry: { x: 0%, y: 0%, w: 100%, h: 100% }
      crop: auto_best
      bleed: true
      constraints:
        avoid_gutter_face: true    # 避免人脸落在中缝（装订线）上
        gutter_safe_zone: 10mm     # 中缝安全区宽度
  text:
    - id: page_number_left
      type: page_number
      position: { x: 5%, y: 95% }  # 左页页码
    - id: page_number_right
      type: page_number
      position: { x: 95%, y: 95% } # 右页页码
  decoration:
    mode: none
```

---

## 5. 裁切模式（crop）

排版引擎根据 `crop` 字段决定照片在槽位内的裁切方式：

| 模式 | 值 | 行为 | 适用场景 |
|------|-----|------|---------|
| **自动最佳** | `auto_best` | 综合显著性热力图 + 人脸框 + 主体框，自动找到最佳裁切框 | 默认模式，适合大部分场景 |
| **人脸居中** | `center_face` | 以人脸为中心裁切，多人时取所有人的包围盒中心 | 小格子图、人像为主的页面 |
| **主体优先** | `subject_first` | 以 YOLO 检测到的主体为中心裁切 | 有明确主体（动物/建筑/车辆）的照片 |
| **中心裁切** | `center` | 以图片几何中心为裁切中心 | 纯风景、无人物照片 |
| **手动裁切** | `manual` | 先按 auto_best 生成初始裁切，用户可在 HITL #2 中手动调整 | 默认初始裁切不满意时 |
| **无裁切** | `none` | 保持图片原始比例，缩放到填满槽位，可能出现留白 | 用户明确要求不裁切时 |

**裁切规则（硬约束）**：
- 任何裁切不得使人脸框被切掉超过 20%
- 任何裁切不得使 YOLO 主体框的中心点落在裁切框外
- 裁切后剩余分辨率不得低于 150 DPI（防止低清图被放大）

---

## 6. 装饰参数（decoration）

### 6.1 装饰模式

| 模式 | 值 | 效果 |
|------|-----|------|
| 无 | `none` | 无任何装饰 |
| 极简 | `minimal` | 仅保留间隙和分隔线 |
| 适中 | `moderate` | 半透明遮罩、装饰线、配色填充 |
| 丰富 | `rich` | 边框花纹、阴影、圆角（二期） |

### 6.2 装饰参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `mode` | enum | 装饰模式 |
| `gap` | value | 照片间距（% 或 mm） |
| `divider` | bool | 是否显示分隔线 |
| `overlay` | object | 半透明遮罩：{ color, opacity } |
| `border` | object | 边框：{ width, color, radius } |
| `shadow` | object | 阴影（二期）：{ offset_x, offset_y, blur, color } |

---

## 7. 文本块（text）

### 7.1 预设位置

| 预设值 | 含义 |
|--------|------|
| `center` | 页面正中央 |
| `top_left` / `top_center` / `top_right` | 顶部左/中/右 |
| `bottom_left` / `bottom_center` / `bottom_right` | 底部左/中/右 |

### 7.2 文本样式

| 参数 | 类型 | 说明 |
|------|------|------|
| `font_size` | value | 字号（pt） |
| `font_family` | string | 字体族 |
| `color` | hex | 颜色 |
| `align` | enum | left / center / right |
| `weight` | enum | normal / bold |
| `max_lines` | int | 最大行数，超出截断 |

---

## 8. 排版引擎如何使用 DSL

```
排版引擎加载 DSL → 获取可用版式列表
        ↓
页面规划器为每页选择版式模板
        ↓
照片分配器按槽位优先级分配照片
        ↓
裁切求解器根据 crop 模式计算每个槽位的最佳裁切框
        ↓
渲染服务根据填充后的版式模板 + 装饰参数生成页面位图
```

**版式选择规则**：
1. 优先匹配 `orientation` 约束（横图优先选支持 landscape 的版式）
2. 章节开头/结尾优先选择 `chapter_cover` 类版式
3. 避免连续 3 页使用同一版式（全书级节奏控制）
4. 相邻页版式尽量不同（相邻页差异度）

---

## 9. 扩展预留

### 9.1 二期版式（暂不实现）

| 版式 | 说明 |
|------|------|
| 四图拼贴（collage_four） | 不规则拼贴，非网格 |
| 对角线叙事（diagonal_story） | 对角线排列，更有动感 |
| 跨页拼版（spread_mosaic） | 跨页多图非对称拼版 |
| 留白大图（large_with_margin） | 大图 + 大面积留白 + 文字 |
| 全景拉页（panorama_foldout） | 三折页全景 |

### 9.2 DSL 版本管理

```yaml
version: "1.0"
changelog:
  - version: "1.0"
    date: "2026-06-01"
    changes: "MVP 初始版本，6 种版式"
  - version: "0.1"
    date: "2026-05-30"
    changes: "草案"
```

---
