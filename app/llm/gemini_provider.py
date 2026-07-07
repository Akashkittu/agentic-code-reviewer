from __future__ import annotations

from app.config import settings
from app.llm.base import LLMResult


class GeminiProvider:
    provider_name = "gemini"

    def generate(self, prompt: str) -> LLMResult:
        if not settings.GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY is missing.")

        try:
            from google import genai

            client = genai.Client(api_key=settings.GEMINI_API_KEY)

            response = client.models.generate_content(
                model=settings.GEMINI_MODEL,
                contents=prompt,
            )

            text = getattr(response, "text", "") or str(response)

            return LLMResult(
                provider=self.provider_name,
                text=text.strip(),
                success=True,
            )

        except Exception as exc:
            raise RuntimeError(f"Gemini provider failed: {exc}") from exc