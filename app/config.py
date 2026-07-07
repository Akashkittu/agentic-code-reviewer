import os

from dotenv import load_dotenv

load_dotenv()


class Settings:
    OPENAI_API_KEY: str | None = os.getenv("OPENAI_API_KEY")
    GEMINI_API_KEY: str | None = os.getenv("GEMINI_API_KEY")
    ANTHROPIC_API_KEY: str | None = os.getenv("ANTHROPIC_API_KEY")

    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    ANTHROPIC_MODEL: str = os.getenv(
        "ANTHROPIC_MODEL",
        "claude-3-5-haiku-latest",
    )

    PRIMARY_LLM: str = os.getenv("PRIMARY_LLM", "openai")

    MAX_LLM_RETRIES: int = int(os.getenv("MAX_LLM_RETRIES", "2"))
    MAX_LANGGRAPH_ITERATIONS: int = int(os.getenv("MAX_LANGGRAPH_ITERATIONS", "4"))
    MAX_FILES_SENT_TO_LLM: int = int(os.getenv("MAX_FILES_SENT_TO_LLM", "20"))
    MAX_SINGLE_FILE_SIZE_KB: int = int(os.getenv("MAX_SINGLE_FILE_SIZE_KB", "100"))


settings = Settings()