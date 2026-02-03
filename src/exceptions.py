"""
Application Exception Hierarchy

Provides structured exceptions for:
- API failures (Riot, Claude)
- Validation errors
- Configuration errors
- Knowledge base errors
"""

from typing import Optional, Any


class LoLCoachError(Exception):
    """Base exception for all LoL Coach errors"""

    def __init__(self, message: str, details: Optional[dict] = None):
        self.message = message
        self.details = details or {}
        super().__init__(message)

    def to_dict(self) -> dict:
        return {
            "error_type": self.__class__.__name__,
            "message": self.message,
            "details": self.details
        }

    def __str__(self) -> str:
        return self.message


# ==================== API Errors ====================

class APIError(LoLCoachError):
    """Base class for API-related errors"""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        response_body: Optional[str] = None,
        **kwargs: Any
    ):
        self.status_code = status_code
        self.response_body = response_body
        details = {"status_code": status_code, **kwargs}
        super().__init__(message, details)


class RiotAPIError(APIError):
    """Riot Games API error"""

    @classmethod
    def not_found(cls, resource: str) -> "RiotAPIError":
        return cls(f"Resource not found: {resource}", status_code=404)

    @classmethod
    def rate_limited(cls, retry_after: Optional[int] = None) -> "RiotAPIError":
        msg = "Rate limited by Riot API"
        if retry_after:
            msg += f". Retry after {retry_after}s"
        return cls(msg, status_code=429, retry_after=retry_after)

    @classmethod
    def unauthorized(cls) -> "RiotAPIError":
        return cls("Invalid or missing Riot API key", status_code=401)

    @classmethod
    def forbidden(cls) -> "RiotAPIError":
        return cls(
            "API key expired or forbidden. Development keys expire every 24 hours. "
            "Get a new one at https://developer.riotgames.com",
            status_code=403
        )

    @classmethod
    def server_error(cls, status_code: int) -> "RiotAPIError":
        return cls(f"Riot API server error (HTTP {status_code})", status_code=status_code)


class ClaudeAPIError(APIError):
    """Anthropic Claude API error"""

    @classmethod
    def rate_limited(cls, retry_after: Optional[int] = None) -> "ClaudeAPIError":
        msg = "Claude API rate limited"
        if retry_after:
            msg += f". Retry after {retry_after}s"
        return cls(msg, status_code=429, retry_after=retry_after)

    @classmethod
    def overloaded(cls) -> "ClaudeAPIError":
        return cls("Claude API is overloaded. Please try again in a moment.", status_code=529)

    @classmethod
    def invalid_request(cls, reason: str) -> "ClaudeAPIError":
        return cls(f"Invalid request to Claude API: {reason}", status_code=400)

    @classmethod
    def context_too_long(cls) -> "ClaudeAPIError":
        return cls(
            "The conversation context is too long for the model. "
            "Try analyzing fewer matches or starting a new conversation.",
            status_code=400,
            reason="context_length"
        )

    @classmethod
    def authentication_failed(cls) -> "ClaudeAPIError":
        return cls(
            "Invalid Anthropic API key. "
            "Get a valid key at https://console.anthropic.com",
            status_code=401
        )

    @classmethod
    def connection_failed(cls) -> "ClaudeAPIError":
        return cls("Failed to connect to Claude API. Check your internet connection.")

    @classmethod
    def timeout(cls) -> "ClaudeAPIError":
        return cls("Claude API request timed out. Please try again.")


# ==================== Validation Errors ====================

class ValidationError(LoLCoachError):
    """Input validation error"""

    def __init__(self, field: str, message: str, value: Any = None):
        self.field = field
        self.value = value
        details = {"field": field}
        if value is not None:
            details["value"] = str(value)[:100]  # Truncate for safety
        super().__init__(message, details)


class InvalidRiotIDError(ValidationError):
    """Invalid Riot ID format"""

    def __init__(self, riot_id: str, reason: Optional[str] = None):
        msg = f"Invalid Riot ID format: '{riot_id}'. Expected 'GameName#TAG'"
        if reason:
            msg += f" ({reason})"
        super().__init__(field="riot_id", message=msg, value=riot_id)


class InvalidPlatformError(ValidationError):
    """Invalid platform/region"""

    def __init__(self, platform: str, valid_platforms: list[str]):
        msg = f"Invalid platform: '{platform}'. Valid platforms: {', '.join(valid_platforms)}"
        super().__init__(field="platform", message=msg, value=platform)
        self.valid_platforms = valid_platforms


class InvalidMatchCountError(ValidationError):
    """Invalid match count"""

    def __init__(self, count: int, min_count: int = 1, max_count: int = 100):
        msg = f"Match count must be between {min_count} and {max_count}, got {count}"
        super().__init__(field="match_count", message=msg, value=count)


# ==================== Knowledge Base Errors ====================

class KnowledgeBaseError(LoLCoachError):
    """Knowledge base loading/access error"""
    pass


class KnowledgeFileNotFoundError(KnowledgeBaseError):
    """Knowledge document not found"""

    def __init__(self, path: str):
        super().__init__(f"Knowledge file not found: {path}", {"path": path})
        self.path = path


class KnowledgeParseError(KnowledgeBaseError):
    """Failed to parse knowledge document"""

    def __init__(self, path: str, reason: str):
        super().__init__(
            f"Failed to parse knowledge file: {path}. Reason: {reason}",
            {"path": path, "reason": reason}
        )
        self.path = path
        self.reason = reason


class KnowledgeLoadError(KnowledgeBaseError):
    """Failed to load knowledge document"""

    def __init__(self, path: str, reason: str):
        super().__init__(
            f"Failed to load knowledge file: {path}. Reason: {reason}",
            {"path": path, "reason": reason}
        )
        self.path = path
        self.reason = reason


# ==================== Configuration Errors ====================

class ConfigurationError(LoLCoachError):
    """Configuration error"""
    pass


class MissingConfigError(ConfigurationError):
    """Required configuration missing"""

    def __init__(self, key: str, hint: Optional[str] = None):
        msg = f"Required configuration missing: {key}"
        if hint:
            msg += f". {hint}"
        super().__init__(msg, {"key": key})
        self.key = key


# ==================== Match Processing Errors ====================

class MatchProcessingError(LoLCoachError):
    """Error processing match data"""
    pass


class PlayerNotFoundInMatchError(MatchProcessingError):
    """Player not found in match data"""

    def __init__(self, puuid: str, match_id: str):
        super().__init__(
            f"Player {puuid[:8]}... not found in match {match_id}",
            {"puuid": puuid, "match_id": match_id}
        )
        self.puuid = puuid
        self.match_id = match_id
