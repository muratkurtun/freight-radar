import json

from openai import OpenAI

from app.config import get_settings
from app.core.errors import AppError
from app.core.logging import get_logger

logger = get_logger(__name__)


class LLMClient:
    """Thin wrapper around the OpenAI Chat Completions API for JSON-only outputs."""

    def __init__(self, *, api_key: str | None = None, model: str | None = None):
        settings = get_settings()
        key = api_key or settings.openai_api_key
        if not key:
            raise AppError("OPENAI_API_KEY is not configured", code="llm_not_configured")
        self._client = OpenAI(api_key=key)
        self._model = model or settings.llm_model

    def complete_json(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int = 1024,
        temperature: float = 0.0,
    ) -> dict:
        response = self._client.chat.completions.create(
            model=self._model,
            max_tokens=max_tokens,
            temperature=temperature,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        text = response.choices[0].message.content or ""
        return _parse_json(text)


def _parse_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        logger.warning("LLM returned non-JSON output: %s", text[:500])
        raise AppError("LLM returned invalid JSON", code="llm_invalid_json") from e
