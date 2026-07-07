from __future__ import annotations

from app.config import settings
from app.llm.base import LLMResult


class ClaudeProvider:
    provider_name = "claude"

    def generate(self, prompt: str) -> LLMResult:
        if not settings.ANTHROPIC_API_KEY:
            raise RuntimeError("ANTHROPIC_API_KEY is missing.")

        try:
            from anthropic import Anthropic

            client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)

            response = client.messages.create(
                model=settings.ANTHROPIC_MODEL,
                max_tokens=1200,
                temperature=0.2,
                messages=[
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
            )

            text_parts: list[str] = []

            for block in response.content:
                block_text = getattr(block, "text", None)
                if block_text:
                    text_parts.append(block_text)

            text = "\n".join(text_parts)

            return LLMResult(
                provider=self.provider_name,
                text=text.strip(),
                success=True,
            )

        except Exception as exc:
            raise RuntimeError(f"Claude provider failed: {exc}") from exc