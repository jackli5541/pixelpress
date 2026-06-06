from __future__ import annotations

from pixelpress_backend.algorithms.chapter_clustering import (
    CLUSTERING_PIPELINE_VERSION,
    PhotoForClustering,
    cluster_chapters,
    compute_cluster_confidence,
    compute_input_hash,
    extract_key_persons,
    extract_scene_tags,
    generate_chapter_title,
    select_cover_photo,
)
from pixelpress_backend.models.workflow_contracts import (
    ChapterClusteringInput,
    ChapterPlan,
    ChapterPlanItem,
    ClusteringSummary,
)
from pixelpress_backend.models.workflow_state import LayoutWorkflowState


"""章节聚类节点。

职责:
- 消费 `state.cleaned_photo_set`。
- 产出 `state.chapter_plan`，供页面规划层使用。

输入:
- `state.cleaned_photo_set`
- `state.request.scene_mode`
- `state.request.constraints`（含 hero_person_id、chapter_count_hint）

输出:
- `state.chapter_plan`
- `state.metadata["chapter_clustering_version"]`
- `state.metadata["chapter_clustering_input_hash"]`

禁止:
- 不要回写 `state.cleaned_photo_set`
- 不要直接生成页面级结构
- 不要改任务状态或布局版本
"""


def chapter_clustering_node(state: LayoutWorkflowState) -> LayoutWorkflowState:
    # 1. 构建输入（与远程代码一致：valid_photos + constraints）
    node_input = ChapterClusteringInput(
        album_id=state.request.album_id,
        scene_mode=state.request.scene_mode,
        valid_photos=state.cleaned_photo_set.valid_photos if state.cleaned_photo_set else [],
        constraints=state.request.constraints,
    )

    # 2. 从 constraints 中提取约束参数
    hero_person_id = node_input.constraints.hero_person_id

    # 3. 转换为算法内部数据结构
    photos_for_clustering = [
        PhotoForClustering(
            photo_id=p.photo_id,
            rank_weight=p.rank_weight,
            captured_at=p.captured_at,
            location_cluster=p.location_cluster,
            person_ids=p.person_ids,
            scene_tags=p.scene_tags,
        )
        for p in node_input.valid_photos
    ]

    # 4. 调用算法
    groups = cluster_chapters(
        photos=photos_for_clustering,
        scene_mode=node_input.scene_mode,
        hero_person_id=hero_person_id,
    )

    # 5. 转换为契约输出
    chapters: list[ChapterPlanItem] = []
    for i, group in enumerate(groups):
        chapters.append(ChapterPlanItem(
            chapter_id=f"chapter-{i + 1:03d}",
            order=i + 1,
            title_candidate=generate_chapter_title(group, node_input.scene_mode, i),
            photo_ids=[p.photo_id for p in group.photos],
            cover_photo_id=select_cover_photo(group.photos),
            time_range=group.time_range,
            cluster_confidence=compute_cluster_confidence(group, node_input.scene_mode),
            degrade_reasons=group.degrade_reasons,
            key_person_ids=extract_key_persons(group.photos),
            scene_tags=extract_scene_tags(group.photos),
        ))

    # 6. 计算 ClusteringSummary
    low_conf = [
        c.chapter_id for c in chapters
        if c.cluster_confidence is not None and c.cluster_confidence < 0.5
    ]
    avg_photos = len(photos_for_clustering) // len(chapters) if chapters else 0

    # 7. 写回 state
    state.chapter_plan = ChapterPlan(
        album_id=node_input.album_id,
        chapters=chapters,
        clustering_summary=ClusteringSummary(
            chapter_count=len(chapters),
            avg_photos_per_chapter=avg_photos,
            low_confidence_chapters=low_conf,
        ),
    )

    # 8. 记录算法版本和输入哈希到 metadata（规范 2.3：可重放）
    state.metadata["chapter_clustering_version"] = CLUSTERING_PIPELINE_VERSION
    state.metadata["chapter_clustering_input_hash"] = compute_input_hash(
        photo_ids=[p.photo_id for p in photos_for_clustering],
        scene_mode=node_input.scene_mode,
        hero_person_id=hero_person_id,
    )

    return state
