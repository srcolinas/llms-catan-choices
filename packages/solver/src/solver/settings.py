import functools
from pathlib import Path

import dotenv
import pydantic
import pydantic_settings


class Settings(pydantic_settings.BaseSettings):
    model_config = pydantic_settings.SettingsConfigDict(
        env_file=".env",
        env_prefix="SOLVER_",
        extra="ignore",
        frozen=True,
    )

    loglevel: str = "INFO"
    """Logging level."""

    llm_model: str
    """pydantic-ai model id in `provider:model` form, e.g. `openai:gpt-4o`."""

    system_one_max_options: int = 15
    """Most placements one System One question may offer. Ollama accepts 26."""

    openai_decision_model: str = "gpt-6-luna"
    """Model id for the OpenAI Decisions API. Only `gpt-6-luna` is available."""

    heuristics: Path
    langfuse_public_key: pydantic.SecretStr | None = None
    langfuse_secret_key: pydantic.SecretStr | None = None
    langfuse_base_url: str | None = None


@functools.cache
def settings() -> Settings:
    dotenv.load_dotenv()
    return Settings()  # type: ignore[call-arg]
