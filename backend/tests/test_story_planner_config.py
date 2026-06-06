from __future__ import annotations

from pixelpress_backend.core.config import Settings

"""故事策划器配置解析测试。

该文件用于验证配置层能否从不同命名风格的环境变量中正确推断
故事策划器的启用状态、提供商、基础地址和模型名称。
"""


def test_settings_enable_story_planner_from_deepseek_env(monkeypatch):
    """当仅提供 DeepSeek 密钥时，应自动推断兼容调用配置。"""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.delenv("DEEPSEEK_BASE_URL", raising=False)
    monkeypatch.delenv("DEEPSEEK_MODEL", raising=False)
    monkeypatch.delenv("PIXELPRESS_STORY_PLANNER_ENABLED", raising=False)

    settings = Settings(_env_file=None)

    assert settings.story_planner_enabled is True
    assert settings.story_planner_provider == "openai_compatible"
    assert settings.story_planner_api_key == "test-key"
    assert settings.story_planner_base_url == "https://api.deepseek.com/v1"
    assert settings.story_planner_model_name == "deepseek-chat"


def test_settings_explicit_pixelpress_story_planner_values_override_generic_env(monkeypatch):
    """显式的 PIXELPRESS_STORY_PLANNER 配置应覆盖通用环境变量。"""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "generic-key")
    monkeypatch.setenv("PIXELPRESS_STORY_PLANNER_ENABLED", "true")
    monkeypatch.setenv("PIXELPRESS_STORY_PLANNER_PROVIDER", "openai_compatible")
    monkeypatch.setenv("PIXELPRESS_STORY_PLANNER_API_KEY", "pixelpress-key")
    monkeypatch.setenv("PIXELPRESS_STORY_PLANNER_BASE_URL", "https://example.com/v1")
    monkeypatch.setenv("PIXELPRESS_STORY_PLANNER_MODEL_NAME", "custom-model")

    settings = Settings(_env_file=None)

    assert settings.story_planner_enabled is True
    assert settings.story_planner_api_key == "pixelpress-key"
    assert settings.story_planner_base_url == "https://example.com/v1"
    assert settings.story_planner_model_name == "custom-model"
