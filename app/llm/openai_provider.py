from __future__ import annotations

from app.config import settings
from app.llm.base import LLMResult


class OpenAIProvider:
    provider_name = "openai"

    def generate(self, prompt: str) -> LLMResult:
        if not settings.OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY is missing.")

        try:
            from openai import OpenAI

            client = OpenAI(api_key=settings.OPENAI_API_KEY)

            response = client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a senior code reviewer. "
                            "Return practical review advice based only on provided repo evidence."
                        ),
                    },
                    {
                        "role": "user",
                        "content": prompt,
                    },
                ],
                temperature=0.2,
            )

            text = response.choices[0].message.content or ""

            return LLMResult(
                provider=self.provider_name,
                text=text.strip(),
                success=True,
            )

        except Exception as exc:
            raise RuntimeError(f"OpenAI provider failed: {exc}") from exc