from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    anthropic_api_key: str = ""
    vapi_phone_number: str = "+1234567890"

    # Browserbase cloud browser
    browserbase_api_key: str = ""
    browserbase_project_id: str = ""

    # Claude model for computer use
    computer_use_model: str = "claude-sonnet-4-20250514"

    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: str = "*"

    code_expiry_minutes: int = 10
    session_timeout_minutes: int = 30

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
