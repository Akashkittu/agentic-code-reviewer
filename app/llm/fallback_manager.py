from __future__ import annotations

from app.config import settings
from app.llm.base import LLMResult
from app.llm.claude_provider import ClaudeProvider
from app.llm.gemini_provider import GeminiProvider
from app.llm.openai_provider import OpenAIProvider


class FallbackLLMManager:
    def __init__(self) -> None:
        providers = {
            "openai": OpenAIProvider(),
            "gemini": GeminiProvider(),
            "claude": ClaudeProvider(),
        }

        primary = settings.PRIMARY_LLM.lower().strip()

        ordered_names = [primary, "openai", "gemini", "claude"]

        seen: set[str] = set()
        self.providers = []

        for name in ordered_names:
            if name in providers and name not in seen:
                self.providers.append(providers[name])
                seen.add(name)

    def generate(self, prompt: str) -> LLMResult:
        attempted: list[str] = []
        errors: list[str] = []

        for provider in self.providers:
            attempted.append(provider.provider_name)

            try:
                result = provider.generate(prompt)
                result.attempted_providers = attempted
                return result

            except Exception as exc:
                errors.append(f"{provider.provider_name}: {exc}")

        static_text = self._static_fallback_text(errors)

        return LLMResult(
            provider="static_fallback",
            text=static_text,
            success=False,
            error=" | ".join(errors),
            attempted_providers=attempted,
        )

    @staticmethod
    def _static_fallback_text(errors: list[str]) -> str:
        return (
            "LLM review was not available, so the workflow continued using "
            "static deterministic tool results only.\n\n"
            "Fallback reason:\n"
            + "\n".join(f"- {error}" for error in errors)
            + "\n\nStatic fallback recommendation:\n"
            "- Fix critical security findings first.\n"
            "- Remove committed secrets and hardcoded keys.\n"
            "- Add tests and README setup instructions.\n"
            "- Re-run the workflow after cleanup."
        )