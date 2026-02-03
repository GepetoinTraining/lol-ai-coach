"""
Unit tests for configuration module.
"""

import pytest
from src.config import (
    get_config,
    validate_config,
    Environment,
    ConfigurationError,
)


class TestGetConfig:
    """Tests for configuration loading"""

    def test_loads_with_valid_env(self, mock_env_vars):
        """Test config loads successfully with valid environment"""
        # Clear cache from previous tests
        get_config.cache_clear()

        config = get_config()

        assert config.riot.api_key == "RGAPI-test-riot-key-12345"
        assert config.claude.api_key == "sk-ant-test-anthropic-key-12345"
        assert config.env == Environment.DEVELOPMENT

    def test_missing_riot_key_raises_error(self, mock_env_vars_missing_riot):
        """Test missing Riot API key raises error"""
        get_config.cache_clear()

        with pytest.raises(ConfigurationError) as exc_info:
            get_config()

        assert "RIOT_API_KEY" in str(exc_info.value)

    def test_missing_anthropic_key_raises_error(self, mock_env_vars_missing_anthropic):
        """Test missing Anthropic API key raises error"""
        get_config.cache_clear()

        with pytest.raises(ConfigurationError) as exc_info:
            get_config()

        assert "ANTHROPIC_API_KEY" in str(exc_info.value)

    def test_defaults_to_development(self, mock_env_vars, monkeypatch):
        """Test defaults to development environment"""
        get_config.cache_clear()
        monkeypatch.delenv("APP_ENV", raising=False)

        config = get_config()
        assert config.env == Environment.DEVELOPMENT

    def test_production_environment(self, mock_env_vars, monkeypatch):
        """Test production environment settings"""
        get_config.cache_clear()
        monkeypatch.setenv("APP_ENV", "production")

        config = get_config()

        assert config.env == Environment.PRODUCTION
        assert config.debug is False
        assert config.logging.json_format is True

    def test_config_is_cached(self, mock_env_vars):
        """Test configuration is cached"""
        get_config.cache_clear()

        config1 = get_config()
        config2 = get_config()

        assert config1 is config2

    def test_cache_can_be_cleared(self, mock_env_vars, monkeypatch):
        """Test cache can be cleared to reload config"""
        get_config.cache_clear()

        config1 = get_config()
        get_config.cache_clear()

        monkeypatch.setenv("LOG_LEVEL", "ERROR")
        config2 = get_config()

        # Config should be different after cache clear
        assert config2.logging.level == "ERROR"

    def test_custom_model_from_env(self, mock_env_vars, monkeypatch):
        """Test custom Claude model from environment"""
        get_config.cache_clear()
        monkeypatch.setenv("CLAUDE_MODEL", "claude-3-opus")

        config = get_config()
        assert config.claude.model == "claude-3-opus"

    def test_custom_timeout_from_env(self, mock_env_vars, monkeypatch):
        """Test custom timeout from environment"""
        get_config.cache_clear()
        monkeypatch.setenv("RIOT_TIMEOUT", "45.0")

        config = get_config()
        assert config.riot.timeout_seconds == 45.0

    def test_custom_rate_limits(self, mock_env_vars, monkeypatch):
        """Test custom rate limits from environment"""
        get_config.cache_clear()
        monkeypatch.setenv("RIOT_RATE_PER_SECOND", "10")
        monkeypatch.setenv("RIOT_RATE_PER_2MIN", "50")

        config = get_config()
        assert config.riot.requests_per_second == 10
        assert config.riot.requests_per_two_minutes == 50


class TestValidateConfig:
    """Tests for configuration validation"""

    def test_valid_config_passes(self, mock_env_vars):
        """Test valid configuration passes validation"""
        get_config.cache_clear()

        result = validate_config()
        assert result is True

    def test_invalid_riot_key_format(self, mock_env_vars, monkeypatch):
        """Test invalid Riot API key format fails validation"""
        get_config.cache_clear()
        monkeypatch.setenv("RIOT_API_KEY", "invalid-key-format")

        with pytest.raises(ConfigurationError) as exc_info:
            validate_config()

        assert "RGAPI-" in str(exc_info.value)

    def test_invalid_anthropic_key_format(self, mock_env_vars, monkeypatch):
        """Test invalid Anthropic API key format fails validation"""
        get_config.cache_clear()
        monkeypatch.setenv("ANTHROPIC_API_KEY", "invalid-key-format")

        with pytest.raises(ConfigurationError) as exc_info:
            validate_config()

        assert "sk-ant-" in str(exc_info.value)


class TestEnvironment:
    """Tests for Environment enum"""

    def test_development_value(self):
        """Test development environment value"""
        assert Environment.DEVELOPMENT.value == "development"

    def test_staging_value(self):
        """Test staging environment value"""
        assert Environment.STAGING.value == "staging"

    def test_production_value(self):
        """Test production environment value"""
        assert Environment.PRODUCTION.value == "production"

    def test_from_string(self):
        """Test creating Environment from string"""
        assert Environment("development") == Environment.DEVELOPMENT
        assert Environment("production") == Environment.PRODUCTION
