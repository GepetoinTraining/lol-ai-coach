"""
Input Validation and Sanitization

Validates and sanitizes all user inputs before API calls.
"""

import re
from urllib.parse import quote
from typing import Tuple

from .exceptions import (
    InvalidRiotIDError,
    InvalidPlatformError,
    InvalidMatchCountError,
    ValidationError,
)


# Valid platforms from Riot API
VALID_PLATFORMS = [
    "na1",   # North America
    "br1",   # Brazil
    "la1",   # Latin America North
    "la2",   # Latin America South
    "euw1",  # EU West
    "eun1",  # EU Nordic & East
    "tr1",   # Turkey
    "ru",    # Russia
    "kr",    # Korea
    "jp1",   # Japan
    "oc1",   # Oceania
    "ph2",   # Philippines
    "sg2",   # Singapore
    "th2",   # Thailand
    "tw2",   # Taiwan
    "vn2",   # Vietnam
]

# Regional routing mapping (same as riot.py)
REGION_ROUTING = {
    "na1": "americas",
    "br1": "americas",
    "la1": "americas",
    "la2": "americas",
    "euw1": "europe",
    "eun1": "europe",
    "tr1": "europe",
    "ru": "europe",
    "kr": "asia",
    "jp1": "asia",
    "oc1": "sea",
    "ph2": "sea",
    "sg2": "sea",
    "th2": "sea",
    "tw2": "sea",
    "vn2": "sea",
}

# Riot ID constraints
# Game name: 3-16 characters, alphanumeric plus spaces, dots, underscores, hyphens
# Tag line: 2-5 alphanumeric characters
MIN_GAME_NAME_LENGTH = 3
MAX_GAME_NAME_LENGTH = 16
MIN_TAG_LENGTH = 2
MAX_TAG_LENGTH = 5

# Match count constraints
MIN_MATCH_COUNT = 1
MAX_MATCH_COUNT = 100


def validate_riot_id(riot_id: str) -> Tuple[str, str]:
    """
    Validate and parse a Riot ID.

    Args:
        riot_id: Raw user input (e.g., "PlayerName#TAG")

    Returns:
        Tuple of (game_name, tag_line) both sanitized

    Raises:
        InvalidRiotIDError: If format is invalid
    """
    if not riot_id or not isinstance(riot_id, str):
        raise InvalidRiotIDError(str(riot_id), "Empty or invalid input")

    riot_id = riot_id.strip()

    if "#" not in riot_id:
        raise InvalidRiotIDError(riot_id, "Missing '#' separator")

    # Split on the last # to handle names with # in them (rare but possible)
    parts = riot_id.rsplit("#", 1)
    if len(parts) != 2:
        raise InvalidRiotIDError(riot_id, "Invalid format")

    game_name = parts[0].strip()
    tag_line = parts[1].strip()

    # Validate game name
    if not game_name:
        raise InvalidRiotIDError(riot_id, "Empty game name")

    if len(game_name) < MIN_GAME_NAME_LENGTH:
        raise InvalidRiotIDError(
            riot_id,
            f"Game name too short (min {MIN_GAME_NAME_LENGTH} characters)"
        )

    if len(game_name) > MAX_GAME_NAME_LENGTH:
        raise InvalidRiotIDError(
            riot_id,
            f"Game name too long (max {MAX_GAME_NAME_LENGTH} characters)"
        )

    # Validate tag line
    if not tag_line:
        raise InvalidRiotIDError(riot_id, "Empty tag line")

    if len(tag_line) < MIN_TAG_LENGTH:
        raise InvalidRiotIDError(
            riot_id,
            f"Tag too short (min {MIN_TAG_LENGTH} characters)"
        )

    if len(tag_line) > MAX_TAG_LENGTH:
        raise InvalidRiotIDError(
            riot_id,
            f"Tag too long (max {MAX_TAG_LENGTH} characters)"
        )

    # Tag must be alphanumeric
    if not tag_line.isalnum():
        raise InvalidRiotIDError(riot_id, "Tag must be alphanumeric")

    return game_name, tag_line


def sanitize_for_url(value: str) -> str:
    """
    URL-encode a value for safe API calls.

    Args:
        value: Raw string to encode

    Returns:
        URL-encoded string safe for use in URLs
    """
    return quote(value, safe="")


def validate_platform(platform: str) -> str:
    """
    Validate a platform identifier.

    Args:
        platform: Raw platform string

    Returns:
        Normalized platform string (lowercase)

    Raises:
        InvalidPlatformError: If platform is not valid
    """
    if not platform or not isinstance(platform, str):
        raise InvalidPlatformError("", VALID_PLATFORMS)

    platform = platform.lower().strip()

    if platform not in VALID_PLATFORMS:
        raise InvalidPlatformError(platform, VALID_PLATFORMS)

    return platform


def get_region_for_platform(platform: str) -> str:
    """
    Get the regional routing value for a platform.

    Args:
        platform: Validated platform string

    Returns:
        Regional routing value (americas, europe, asia, sea)
    """
    return REGION_ROUTING.get(platform.lower(), "americas")


def validate_match_count(count: int) -> int:
    """
    Validate match count is within acceptable range.

    Args:
        count: Number of matches to analyze

    Returns:
        Validated match count

    Raises:
        InvalidMatchCountError: If count is out of range
    """
    if not isinstance(count, int):
        try:
            count = int(count)
        except (ValueError, TypeError):
            raise InvalidMatchCountError(0, MIN_MATCH_COUNT, MAX_MATCH_COUNT)

    if count < MIN_MATCH_COUNT:
        raise InvalidMatchCountError(count, MIN_MATCH_COUNT, MAX_MATCH_COUNT)

    if count > MAX_MATCH_COUNT:
        raise InvalidMatchCountError(count, MIN_MATCH_COUNT, MAX_MATCH_COUNT)

    return count


def sanitize_game_name(game_name: str) -> str:
    """
    Sanitize a game name for logging (remove potential PII concerns).

    Args:
        game_name: Raw game name

    Returns:
        Partially masked game name for logging
    """
    if not game_name:
        return "<empty>"

    if len(game_name) <= 4:
        return game_name[0] + "*" * (len(game_name) - 1)

    # Show first 2 and last 2 characters
    return game_name[:2] + "*" * (len(game_name) - 4) + game_name[-2:]


def validate_intent(intent: str, valid_intents: list[str]) -> str:
    """
    Validate a coaching intent value.

    Args:
        intent: Raw intent string
        valid_intents: List of valid intent values

    Returns:
        Validated intent string

    Raises:
        ValidationError: If intent is not valid
    """
    if not intent or not isinstance(intent, str):
        raise ValidationError("intent", "Intent is required", intent)

    intent = intent.lower().strip()

    if intent not in valid_intents:
        raise ValidationError(
            "intent",
            f"Invalid intent. Valid options: {', '.join(valid_intents)}",
            intent
        )

    return intent
