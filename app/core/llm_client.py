from __future__ import annotations

from typing import Any

import httpx

from app.config import MODEL_PROFILES, Settings


class OpenAICompatibleClient:
    def __init__(self, settings: Settings):
        self.base_url = settings.openai_base_url.rstrip("/")
        self.api_key = settings.openai_api_key
        self.timeout = settings.request_timeout_seconds

    async def chat(self, model_profile: str, prompt: str, temperature: float) -> dict[str, Any]:
        profile = MODEL_PROFILES.get(model_profile)
        if profile is None:
            raise ValueError(f"Unknown model profile: {model_profile}")
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured")

        payload = {
            "model": profile.model_id,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(f"{self.base_url}/chat/completions", json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

        content = data["choices"][0]["message"]["content"]
        usage = data.get("usage")
        return {"model": profile.model_id, "content": content, "usage": usage}
