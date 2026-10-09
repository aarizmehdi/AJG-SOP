"""Comparison-matrix configuration."""

from pathlib import Path
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RetrievalConfig(BaseModel):
    """One retrieval configuration to benchmark.

    Defaults describe today's product pipeline (section chunker, reciprocal-rank fusion with equal
    weights, fixture reranker) with a deterministic stand-in embedding.
    """

    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1)
    description: str = ""
    chunker: str = "current"
    embedding: str = "fixture-hash"
    reranker: str = "fixture"
    lexical: bool = True
    semantic: bool = True
    lexical_weight: float = Field(default=1.0, ge=0)
    semantic_weight: float = Field(default=1.0, ge=0)
    rank_constant: int = Field(default=60, ge=1)
    candidate_pool: int | None = Field(default=None, ge=1)
    assistant: bool = True

    @model_validator(mode="after")
    def at_least_one_channel(self) -> Self:
        if not (self.lexical or self.semantic):
            raise ValueError("A configuration needs at least one candidate channel")
        return self


class MatrixSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ks: list[int] = Field(default=[1, 3, 5, 10], min_length=1)
    primary_k: int = 5
    configs: list[RetrievalConfig]

    @model_validator(mode="after")
    def validate_matrix(self) -> Self:
        if self.primary_k not in self.ks:
            raise ValueError("primary_k must be one of ks")
        if any(k < 1 for k in self.ks):
            raise ValueError("Every k must be positive")
        names = [config.name for config in self.configs]
        if len(set(names)) != len(names):
            raise ValueError("Configuration names must be unique")
        if not self.configs:
            raise ValueError("At least one configuration is required")
        return self


def load_matrix(path: Path) -> MatrixSpec:
    return MatrixSpec.model_validate_json(path.read_text(encoding="utf-8"))
