from app.engines.chapter_engine.prompt_pipeline import _build_user_prompt, normalize_chapter_name


def test_chapter_naming_prompt_treats_dates_as_metadata_not_titles():
    chapter = {
        "chapter_key": "chapter-1",
        "name": "第 1 章",
        "time_range": "2024年6月13日",
        "clustering_explanation": {"representative_photo_ids": ["first"]},
    }
    photos = [{
        "id": "first",
        "filename": "first.jpg",
        "taken_at": "2024-06-13T09:00:00",
        "gps_latitude": None,
        "gps_longitude": None,
        "scene_tags": [],
    }]

    prompt = _build_user_prompt(chapter, photos, 1)

    assert "名称中不要写具体年月日" in prompt
    assert "不要机械复述 time_range" in prompt
    assert "time_range=2024年6月13日" in prompt


def test_chapter_name_normalization_removes_calendar_prefix_but_keeps_time_of_day():
    assert normalize_chapter_name("2024年6月13日：山间古建与石阶", "第 1 章") == "山间古建与石阶"
    assert normalize_chapter_name("2024年6月13日傍晚的古镇街景", "第 2 章") == "傍晚的古镇街景"
    assert normalize_chapter_name("2024-06-13 · 溪谷漫步", "第 3 章") == "溪谷漫步"
    assert normalize_chapter_name("2024年6月13日", "第 4 章") == "第 4 章"
    assert normalize_chapter_name("夜间灯火与街市", "第 5 章") == "夜间灯火与街市"
