from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env.local", ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    app_mode: Literal["fixture", "live"] = "fixture"
    app_env: str = "development"
    app_name: str = "Aziz Jan Group SOP Knowledge System"
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
    s3_access_key_id: SecretStr | None = Field(
        default=None, validation_alias=AliasChoices("s3_access_key_id", "s3_access_key")
    )
    s3_secret_access_key: SecretStr | None = Field(
        default=None, validation_alias=AliasChoices("s3_secret_access_key", "s3_secret_key")
    )

    pinecone_api_key: SecretStr | None = None
    pinecone_index_name: str = Field(
        default="aziz-jan-sop", validation_alias=AliasChoices("pinecone_index_name", "pinecone_index")
    )
    pinecone_environment: str = "gcp-starter"
    pinecone_dimension: int = 1024
    pinecone_namespace_prefix: str = "aziz-jan-trust"

    firebase_project_id: str | None = None
    firebase_service_account_json: SecretStr | None = None

    llm_provider: Literal["fixture", "deepseek", "groq"] = "groq"
    deepseek_api_key: SecretStr | None = None
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-flash"
    deepseek_temperature: float = Field(default=0.2, ge=0, le=1)

    groq_api_key: SecretStr | None = None
    groq_model_name: str = "llama-3.3-70b-versatile"

    embedding_provider: Literal["fixture", "e5"] = "e5"
    e5_model_name: str = "multilingual-e5-large"
    e5_passage_prefix: str = "passage: "
    e5_query_prefix: str = "query: "
    reranker_provider: str = "fixture"
    document_parser_provider: Literal["fixture", "azure", "docling", "auto"] = "fixture"
    speech_provider: Literal["disabled"] = "disabled"

    azure_document_intelligence_endpoint: str | None = None
    azure_document_intelligence_key: SecretStr | None = None

    @property
    def allowed_origins(self) -> list[str]:
        """Return the list of allowed CORS origins."""
        raw_origins = [self.web_origin.rstrip("/")]
        if self.cors_origins:
            raw_origins.extend(
                origin.strip().rstrip("/")
                for origin in self.cors_origins.split(",")
                if origin.strip()
            )
        extended: list[str] = []
        for origin in raw_origins:
            if origin:
                extended.append(origin)
                extended.append(f"{origin}/")
        return list(dict.fromkeys(extended))

    @model_validator(mode="after")
    def validate_live_configuration(self) -> "Settings":
        if self.app_mode == "live":
            required = {
                "FIREBASE_PROJECT_ID": self.firebase_project_id,
                "FIREBASE_SERVICE_ACCOUNT_JSON": self.firebase_service_account_json,
                "S3_ACCESS_KEY_ID": self.s3_access_key_id,
                "S3_SECRET_ACCESS_KEY": self.s3_secret_access_key,
            }
            missing = [name for name, value in required.items() if not value]
            if missing:
                raise ValueError(f"Missing required live configuration: {', '.join(missing)}")
            if self.embedding_provider != "e5":
                raise ValueError("EMBEDDING_PROVIDER must be e5 in live mode")
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
