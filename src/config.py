"""
Centralized Configuration Management

Loads configuration from environment variables with sensible defaults.
Supports development, staging, and production environments.
"""

import os
from dataclasses import dataclass
from typing import Optional
from enum import Enum
from functools import lru_cache


class Environment(Enum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


@dataclass(frozen=True)
class RiotAPIConfig:
    """Riot API configuration"""
    api_key: str
    default_region: str = "americas"
    timeout_seconds: float = 30.0
    requests_per_second: int = 20
    requests_per_two_minutes: int = 100
    max_retries: int = 3
    retry_min_wait: float = 1.0
    retry_max_wait: float = 10.0


@dataclass(frozen=True)
class ClaudeConfig:
    """Claude API configuration"""
    api_key: str
    model: str = "claude-sonnet-4-20250514"
    max_tokens_analysis: int = 1500
    max_tokens_chat: int = 1000
    max_tokens_exercise: int = 800
    timeout_seconds: float = 60.0
    max_retries: int = 3


@dataclass(frozen=True)
class DatabaseConfig:
    """Database configuration"""
    url: str = "sqlite:///./data/lol_coach.db"
    echo: bool = False


@dataclass(frozen=True)
class LoggingConfig:
    """Logging configuration"""
    level: str = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    json_format: bool = False
    log_file: Optional[str] = None


@dataclass(frozen=True)
class AppConfig:
    """Root application configuration"""
    env: Environment
    riot: RiotAPIConfig
    claude: ClaudeConfig
    database: DatabaseConfig
    logging: LoggingConfig
    debug: bool = False


class ConfigurationError(Exception):
    """Raised when configuration is invalid or missing"""
    pass


def _get_env(key: str, default: Optional[str] = None, required: bool = False) -> Optional[str]:
    """Get environment variable with optional requirement check"""
    value = os.getenv(key, default)
    if required and not value:
        raise ConfigurationError(f"Required environment variable {key} is not set")
    return value


def _get_env_bool(key: str, default: bool = False) -> bool:
    """Get boolean environment variable"""
    value = os.getenv(key, "").lower()
    if value in ("true", "1", "yes"):
        return True
    if value in ("false", "0", "no"):
        return False
    return default


def _get_env_int(key: str, default: int) -> int:
    """Get integer environment variable"""
    value = os.getenv(key)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _get_env_float(key: str, default: float) -> float:
    """Get float environment variable"""
    value = os.getenv(key)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


@lru_cache(maxsize=1)
def get_config() -> AppConfig:
    """
    Load and cache application configuration.

    Uses @lru_cache to ensure config is loaded once and reused.
    Call get_config.cache_clear() to reload configuration.
    """
    env_str = _get_env("APP_ENV", "development")
    try:
        env = Environment(env_str.lower())
    except ValueError:
        env = Environment.DEVELOPMENT

    is_prod = env == Environment.PRODUCTION

    # Riot API config - key is required
    riot_key = _get_env("RIOT_API_KEY")
    if not riot_key:
        raise ConfigurationError(
            "RIOT_API_KEY is required. Get one at https://developer.riotgames.com"
        )

    # Claude API config - key is required
    claude_key = _get_env("ANTHROPIC_API_KEY")
    if not claude_key:
        raise ConfigurationError(
            "ANTHROPIC_API_KEY is required. Get one at https://console.anthropic.com"
        )

    return AppConfig(
        env=env,
        debug=_get_env_bool("DEBUG", default=not is_prod),
        riot=RiotAPIConfig(
            api_key=riot_key,
            default_region=_get_env("RIOT_DEFAULT_REGION", "americas"),
            timeout_seconds=_get_env_float("RIOT_TIMEOUT", 30.0),
            requests_per_second=_get_env_int("RIOT_RATE_PER_SECOND", 20),
            requests_per_two_minutes=_get_env_int("RIOT_RATE_PER_2MIN", 100),
            max_retries=_get_env_int("RIOT_MAX_RETRIES", 3),
        ),
        claude=ClaudeConfig(
            api_key=claude_key,
            model=_get_env("CLAUDE_MODEL", "claude-sonnet-4-20250514"),
            max_tokens_analysis=_get_env_int("CLAUDE_MAX_TOKENS_ANALYSIS", 1500),
            max_tokens_chat=_get_env_int("CLAUDE_MAX_TOKENS_CHAT", 1000),
            max_tokens_exercise=_get_env_int("CLAUDE_MAX_TOKENS_EXERCISE", 800),
            timeout_seconds=_get_env_float("CLAUDE_TIMEOUT", 60.0),
            max_retries=_get_env_int("CLAUDE_MAX_RETRIES", 3),
        ),
        database=DatabaseConfig(
            url=_get_env("DATABASE_URL", "sqlite:///./data/lol_coach.db"),
            echo=_get_env_bool("DATABASE_ECHO", False),
        ),
        logging=LoggingConfig(
            level=_get_env("LOG_LEVEL", "DEBUG" if not is_prod else "INFO"),
            json_format=is_prod,
            log_file=_get_env("LOG_FILE"),
        ),
    )


def validate_config() -> bool:
    """
    Validate configuration on startup.

    Returns True if valid, raises ConfigurationError if not.
    """
    try:
        config = get_config()

        # Validate API keys have reasonable format
        if not config.riot.api_key.startswith("RGAPI-"):
            raise ConfigurationError(
                "RIOT_API_KEY should start with 'RGAPI-'. "
                "Get a valid key at https://developer.riotgames.com"
            )

        if not config.claude.api_key.startswith("sk-ant-"):
            raise ConfigurationError(
                "ANTHROPIC_API_KEY should start with 'sk-ant-'. "
                "Get a valid key at https://console.anthropic.com"
            )

        return True

    except ConfigurationError:
        raise
    except Exception as e:
        raise ConfigurationError(f"Configuration validation failed: {e}")
