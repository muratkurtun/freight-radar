import json

from anthropic import Anthropic

from app.config import get_settings
from app.core.errors import AppError
from app.core.logging import get_logger

logger = get_logger(__name__)


class LLMClient:
    """Thin wrapper around the Anthropic Messages API for JSON-only outputs."""

    def __init__(self, *, api_key: str | None = None, model: str | None = None):
        settings = get_settings()
        key = api_key or settings.anthropic_api_key
        if not key:
            raise AppError("ANTHROPIC_API_KEY is not configured", code="llm_not_configured")
        self._client = Anthropic(api_key=key)
        self._model = model or settings.llm_model

    def complete_json(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int = 1024,
        temperature: float = 0.0,
    ) -> dict:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(block.text for block in response.content if getattr(block, "type", None) == "text")
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
