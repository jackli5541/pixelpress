from pixelpress_backend.graph.chapter_clustering_node import chapter_clustering_node


def test_chapter_clustering_node_uses_cleaned_photo_set(
    workflow_state_factory,
    cleaned_photo_set_fixture,
):
    state = workflow_state_factory(cleaned_photo_set=cleaned_photo_set_fixture)

    result = chapter_clustering_node(state)

    assert result.chapter_plan.album_id == "album-test"
    assert len(result.chapter_plan.chapters) == 1
    assert result.chapter_plan.chapters[0].photo_ids == ["p1", "p2", "p3"]
