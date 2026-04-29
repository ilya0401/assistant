from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    claude_api_key: str = ""
    jira_api_token: str = ""
    jira_token_file: str = ""
    jira_url: str = ""
    jira_email: str = ""
    whisper_model: str = "base"
    os_type: str = "macos"
    data_dir: str = "/data"

    class Config:
        env_file = ".env"


settings = Settings()