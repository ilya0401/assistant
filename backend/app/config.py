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
    postgres_db: str = "vinnie"
    postgres_user: str = "vinnie"
    postgres_password: str = ""
    db_host: str = "db"
    db_port: int = 5432

    class Config:
        env_file = ".env"


settings = Settings()