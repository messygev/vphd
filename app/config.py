from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ModelProfile:
    key: str
    label: str
    model_id: str
    description: str


@dataclass(frozen=True)
class Settings:
    db_path: str
    openai_base_url: str
    openai_api_key: str
    request_timeout_seconds: float


MODEL_PROFILES: dict[str, ModelProfile] = {
    "small": ModelProfile(
        key="small",
        label="Small",
        model_id=os.getenv("MODEL_SMALL", "small-3b"),
        description="Kostengünstig für einfache Aufgaben.",
    ),
    "fast": ModelProfile(
        key="fast",
        label="Fast 3B",
        model_id=os.getenv("MODEL_FAST", "fast-3b"),
        description="Sehr schnelle Antworten mit niedrigster Latenz.",
    ),
    "mid": ModelProfile(
        key="mid",
        label="Mid (OSS 120B)",
        model_id=os.getenv("MODEL_MID", "gpt-oss-120b"),
        description="Ausgewogen für komplexere Retrieval-Tasks.",
    ),
    "enterprise": ModelProfile(
        key="enterprise",
        label="Enterprise (GPT-5.4)",
        model_id=os.getenv("MODEL_ENTERPRISE", "gpt-5.4"),
        description="Höchste Qualität für kritische Entscheidungen.",
    ),
}


def get_settings() -> Settings:
    return Settings(
        db_path=os.getenv("BRAIN_DB_PATH", "braindump.db"),
        openai_base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        request_timeout_seconds=float(os.getenv("OPENAI_TIMEOUT", "20")),
    )
