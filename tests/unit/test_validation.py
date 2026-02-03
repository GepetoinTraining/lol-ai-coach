"""
Unit tests for input validation module.
"""

import pytest
from src.validation import (
    validate_riot_id,
    validate_platform,
    validate_match_count,
    sanitize_for_url,
    sanitize_game_name,
    get_region_for_platform,
    VALID_PLATFORMS,
)
from src.exceptions import (
    InvalidRiotIDError,
    InvalidPlatformError,
    InvalidMatchCountError,
)


class TestValidateRiotID:
    """Tests for Riot ID validation"""

    def test_valid_riot_id_simple(self):
        """Test parsing simple valid Riot ID"""
        name, tag = validate_riot_id("Player#TAG")
        assert name == "Player"
        assert tag == "TAG"

    def test_valid_riot_id_with_spaces(self):
        """Test Riot ID with spaces in name"""
        name, tag = validate_riot_id("Cool Player#BR1")
        assert name == "Cool Player"
        assert tag == "BR1"

    def test_valid_riot_id_with_numbers(self):
        """Test Riot ID with numbers"""
        name, tag = validate_riot_id("Player123#ABC")
        assert name == "Player123"
        assert tag == "ABC"

    def test_valid_riot_id_min_length(self):
        """Test Riot ID with minimum lengths"""
        name, tag = validate_riot_id("Abc#AB")
        assert name == "Abc"
        assert tag == "AB"

    def test_valid_riot_id_max_length(self):
        """Test Riot ID with maximum lengths"""
        name, tag = validate_riot_id("SixteenCharName!#ABCDE")
        assert name == "SixteenCharName!"
        assert tag == "ABCDE"

    def test_valid_riot_id_special_chars_in_name(self):
        """Test Riot ID with special characters in name"""
        name, tag = validate_riot_id("Player_Name-123#TAG")
        assert name == "Player_Name-123"
        assert tag == "TAG"

    def test_strips_whitespace(self):
        """Test whitespace is stripped"""
        name, tag = validate_riot_id("  Player  #  TAG  ")
        assert name == "Player"
        assert tag == "TAG"

    def test_invalid_missing_hash(self):
        """Test missing # separator"""
        with pytest.raises(InvalidRiotIDError) as exc_info:
            validate_riot_id("PlayerTAG")
        assert "Missing '#' separator" in str(exc_info.value)

    def test_invalid_empty_string(self):
        """Test empty string"""
        with pytest.raises(InvalidRiotIDError):
            validate_riot_id("")

    def test_invalid_none(self):
        """Test None input"""
        with pytest.raises(InvalidRiotIDError):
            validate_riot_id(None)

    def test_invalid_empty_name(self):
        """Test empty game name"""
        with pytest.raises(InvalidRiotIDError) as exc_info:
            validate_riot_id("#TAG")
        assert "Empty game name" in str(exc_info.value)

    def test_invalid_empty_tag(self):
        """Test empty tag line"""
        with pytest.raises(InvalidRiotIDError) as exc_info:
            validate_riot_id("Player#")
        assert "Empty tag line" in str(exc_info.value)

    def test_invalid_name_too_short(self):
        """Test name shorter than 3 characters"""
        with pytest.raises(InvalidRiotIDError) as exc_info:
            validate_riot_id("AB#TAG")
        assert "too short" in str(exc_info.value)

    def test_invalid_name_too_long(self):
        """Test name longer than 16 characters"""
        with pytest.raises(InvalidRiotIDError) as exc_info:
            validate_riot_id("ThisNameIsWayTooLong#TAG")
        assert "too long" in str(exc_info.value)

    def test_invalid_tag_too_short(self):
        """Test tag shorter than 2 characters"""
        with pytest.raises(InvalidRiotIDError) as exc_info:
            validate_riot_id("Player#A")
        assert "too short" in str(exc_info.value)

    def test_invalid_tag_too_long(self):
        """Test tag longer than 5 characters"""
        with pytest.raises(InvalidRiotIDError) as exc_info:
            validate_riot_id("Player#TOOLONG")
        assert "too long" in str(exc_info.value)

    def test_invalid_tag_not_alphanumeric(self):
        """Test tag with non-alphanumeric characters"""
        with pytest.raises(InvalidRiotIDError) as exc_info:
            validate_riot_id("Player#TA-G")
        assert "alphanumeric" in str(exc_info.value)

    def test_multiple_hash_signs(self):
        """Test Riot ID with multiple # (uses last one)"""
        name, tag = validate_riot_id("Name#With#Hash#TAG")
        assert name == "Name#With#Hash"
        assert tag == "TAG"


class TestValidatePlatform:
    """Tests for platform validation"""

    @pytest.mark.parametrize("platform", VALID_PLATFORMS)
    def test_valid_platforms(self, platform):
        """Test all valid platforms"""
        result = validate_platform(platform)
        assert result == platform.lower()

    def test_case_insensitive(self):
        """Test platform validation is case-insensitive"""
        assert validate_platform("NA1") == "na1"
        assert validate_platform("BR1") == "br1"
        assert validate_platform("EUW1") == "euw1"

    def test_strips_whitespace(self):
        """Test whitespace is stripped"""
        assert validate_platform("  na1  ") == "na1"

    def test_invalid_platform(self):
        """Test invalid platform raises error"""
        with pytest.raises(InvalidPlatformError) as exc_info:
            validate_platform("invalid")
        assert "invalid" in str(exc_info.value).lower()
        assert exc_info.value.valid_platforms == VALID_PLATFORMS

    def test_invalid_empty(self):
        """Test empty string raises error"""
        with pytest.raises(InvalidPlatformError):
            validate_platform("")

    def test_invalid_none(self):
        """Test None raises error"""
        with pytest.raises(InvalidPlatformError):
            validate_platform(None)


class TestValidateMatchCount:
    """Tests for match count validation"""

    def test_valid_count_minimum(self):
        """Test minimum valid match count"""
        assert validate_match_count(1) == 1

    def test_valid_count_maximum(self):
        """Test maximum valid match count"""
        assert validate_match_count(100) == 100

    def test_valid_count_typical(self):
        """Test typical match count"""
        assert validate_match_count(20) == 20

    def test_valid_count_string_conversion(self):
        """Test string is converted to int"""
        assert validate_match_count("50") == 50

    def test_invalid_zero(self):
        """Test zero is invalid"""
        with pytest.raises(InvalidMatchCountError):
            validate_match_count(0)

    def test_invalid_negative(self):
        """Test negative is invalid"""
        with pytest.raises(InvalidMatchCountError):
            validate_match_count(-5)

    def test_invalid_too_large(self):
        """Test over 100 is invalid"""
        with pytest.raises(InvalidMatchCountError):
            validate_match_count(101)

    def test_invalid_non_numeric_string(self):
        """Test non-numeric string is invalid"""
        with pytest.raises(InvalidMatchCountError):
            validate_match_count("abc")


class TestSanitizeForUrl:
    """Tests for URL sanitization"""

    def test_encodes_spaces(self):
        """Test spaces are encoded"""
        assert sanitize_for_url("Cool Player") == "Cool%20Player"

    def test_encodes_special_chars(self):
        """Test special characters are encoded"""
        assert sanitize_for_url("Player+Test") == "Player%2BTest"
        assert sanitize_for_url("Name&Tag") == "Name%26Tag"

    def test_encodes_slashes(self):
        """Test slashes are encoded"""
        result = sanitize_for_url("Test/Path")
        assert "/" not in result
        assert result == "Test%2FPath"

    def test_simple_alphanumeric(self):
        """Test simple alphanumeric passes through"""
        # Note: even safe chars are encoded for maximum safety
        result = sanitize_for_url("Player123")
        assert "Player" in result or "%50" in result  # P can be encoded

    def test_unicode_characters(self):
        """Test unicode characters are encoded"""
        result = sanitize_for_url("Playe")
        assert "%" in result  # Unicode should be percent-encoded


class TestSanitizeGameName:
    """Tests for game name sanitization for logging"""

    def test_short_name(self):
        """Test short name masking"""
        assert sanitize_game_name("ABC") == "A**"
        assert sanitize_game_name("ABCD") == "A***"

    def test_longer_name(self):
        """Test longer name shows first 2 and last 2"""
        result = sanitize_game_name("TestPlayer")
        assert result.startswith("Te")
        assert result.endswith("er")
        assert "*" in result

    def test_empty_name(self):
        """Test empty name returns placeholder"""
        assert sanitize_game_name("") == "<empty>"
        assert sanitize_game_name(None) == "<empty>"


class TestGetRegionForPlatform:
    """Tests for platform to region mapping"""

    def test_americas_platforms(self):
        """Test Americas region platforms"""
        assert get_region_for_platform("na1") == "americas"
        assert get_region_for_platform("br1") == "americas"
        assert get_region_for_platform("la1") == "americas"

    def test_europe_platforms(self):
        """Test Europe region platforms"""
        assert get_region_for_platform("euw1") == "europe"
        assert get_region_for_platform("eun1") == "europe"
        assert get_region_for_platform("tr1") == "europe"

    def test_asia_platforms(self):
        """Test Asia region platforms"""
        assert get_region_for_platform("kr") == "asia"
        assert get_region_for_platform("jp1") == "asia"

    def test_sea_platforms(self):
        """Test SEA region platforms"""
        assert get_region_for_platform("oc1") == "sea"
        assert get_region_for_platform("sg2") == "sea"

    def test_unknown_defaults_americas(self):
        """Test unknown platform defaults to americas"""
        assert get_region_for_platform("unknown") == "americas"
