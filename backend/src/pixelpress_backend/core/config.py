from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "PixelPress Backend"
    app_version: str = "0.1.0"
    api_prefix: str = "/api/v1"
    default_book_size: str = "A4_square"
    default_binding: str = "hardcover"
    default_style: str = "minimal"

    model_config = SettingsConfigDict(
        env_prefix="PIXELPRESS_",
        env_file=".env",
        extra="ignore",
    )


settings = Settings()
