from functools import lru_cache
from typing import Literal

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env.local", ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    app_mode: Literal["fixture", "live"] = "fixture"
    app_env: str = "development"
    app_name: str = "Aziz Jan Trust SOP Knowledge System"
    api_prefix: str = "/api/v1"
    web_origin: str = "http://localhost:5173"
    cors_origins: str = ""

    port: int = 8000
    workers: int = 1
    max_upload_bytes: int = 200 * 1024 * 1024

    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_database: str = "aziz_jan_sop"
    redis_url: str = "redis://localhost:6379/0"

    s3_endpoint_url: str | None = None
    s3_region: str = "us-east-1"
    s3_bucket: str = "aziz-jan-sop-private"
    s3_access_key_id: SecretStr | None = None
    s3_secret_access_key: SecretStr | None = None

    pinecone_api_key: SecretStr | None = None
    pinecone_index: str = "aziz-jan-sop"
    pinecone_namespace_prefix: str = "aziz-jan-trust"

    auth0_domain: str | None = None
    auth0_audience: str | None = None
    auth0_client_id: str | None = None

    llm_provider: Literal["fixture", "deepseek"] = "deepseek"
    deepseek_api_key: SecretStr | None = None
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-v4-flash"

    embedding_provider: str = "fixture"
    embedding_model: str = "provisional-multilingual"
    reranker_provider: str = "fixture"
    document_parser_provider: Literal["fixture", "azure", "docling", "auto"] = "fixture"
    speech_provider: Literal["disabled"] = "disabled"

    azure_document_intelligence_endpoint: str | None = None
    azure_document_intelligence_key: SecretStr | None = None

    @property
    def allowed_origins(self) -> list[str]:
        """Return the list of allowed CORS origins."""
        origins = [self.web_origin]
        if self.cors_origins:
            origins.extend(
                origin.strip() for origin in self.cors_origins.split(",") if origin.strip()
            )
        return origins

    @model_validator(mode="after")
    def validate_live_configuration(self) -> "Settings":
        if self.app_mode == "live":
            required = {
                "AUTH0_DOMAIN": self.auth0_domain,
                "AUTH0_AUDIENCE": self.auth0_audience,
                "AUTH0_CLIENT_ID": self.auth0_client_id,
                "PINECONE_API_KEY": self.pinecone_api_key,
                "S3_ACCESS_KEY_ID": self.s3_access_key_id,
                "S3_SECRET_ACCESS_KEY": self.s3_secret_access_key,
            }
            missing = [name for name, value in required.items() if not value]
            if missing:
                raise ValueError(f"Missing required live configuration: {', '.join(missing)}")
            if "localhost" in self.web_origin:
                raise ValueError(
                    "WEB_ORIGIN must not be localhost in live mode; "
                    "set it to your production Vercel URL"
                )
            if "localhost" in self.mongodb_uri and "127.0.0.1" not in self.mongodb_uri:
                pass  # Allow explicit localhost for local live testing
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
