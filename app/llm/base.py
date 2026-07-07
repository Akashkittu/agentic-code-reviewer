from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class LLMResult:
    provider: str
    text: str
    success: bool
    error: str | None = None
    attempted_providers: list[str] = field(default_factory=list)


class LLMProvider(Protocol):
    provider_name: str

    def generate(self, prompt: str) -> LLMResult:
        ...