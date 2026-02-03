"""
Shared test fixtures for LoL AI Coach tests.
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import Mock, AsyncMock

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


@pytest.fixture
def mock_env_vars(monkeypatch):
    """Set up mock environment variables for testing"""
    monkeypatch.setenv("RIOT_API_KEY", "RGAPI-test-riot-key-12345")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-anthropic-key-12345")
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")


@pytest.fixture
def mock_env_vars_missing_riot(monkeypatch):
    """Environment without Riot API key"""
    monkeypatch.delenv("RIOT_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key")


@pytest.fixture
def mock_env_vars_missing_anthropic(monkeypatch):
    """Environment without Anthropic API key"""
    monkeypatch.setenv("RIOT_API_KEY", "RGAPI-test-key")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


@pytest.fixture
def sample_match_data():
    """Return sample match data structure"""
    from tests.fixtures.sample_matches import SAMPLE_MATCH_RESPONSE
    return SAMPLE_MATCH_RESPONSE


@pytest.fixture
def sample_player_info():
    """Return sample player info structure"""
    return {
        "account": {
            "puuid": "test-puuid-12345",
            "gameName": "TestPlayer",
            "tagLine": "TEST"
        },
        "summoner": {
            "id": "summoner-id-123",
            "accountId": "account-id-456",
            "puuid": "test-puuid-12345",
            "summonerLevel": 150
        },
        "league": [
            {
                "queueType": "RANKED_SOLO_5x5",
                "tier": "GOLD",
                "rank": "II",
                "leaguePoints": 50,
                "wins": 100,
                "losses": 90
            }
        ]
    }


@pytest.fixture
def mock_anthropic_client():
    """Mock Anthropic client for testing"""
    mock_client = Mock()
    mock_response = Mock()
    mock_response.content = [Mock(text="Test coaching response from Claude")]
    mock_response.usage = Mock(input_tokens=100, output_tokens=200)
    mock_client.messages.create.return_value = mock_response
    return mock_client


@pytest.fixture
def mock_httpx_client():
    """Mock httpx client for Riot API testing"""
    mock_client = AsyncMock()
    return mock_client


@pytest.fixture
def knowledge_temp_dir(tmp_path):
    """Create temporary knowledge directory with sample files"""
    knowledge_dir = tmp_path / "knowledge"
    knowledge_dir.mkdir()

    # Create sample knowledge files
    fundamentals = knowledge_dir / "fundamentals"
    fundamentals.mkdir()

    (fundamentals / "wave_management.md").write_text(
        "# Wave Management\n\nBasic wave management principles for laning phase.",
        encoding="utf-8"
    )

    (fundamentals / "trading.md").write_text(
        "# Trading Fundamentals\n\nHow to trade effectively in lane.",
        encoding="utf-8"
    )

    # Create mental category
    mental = knowledge_dir / "mental"
    mental.mkdir()

    (mental / "vod_review.md").write_text(
        "# VOD Review Guide\n\nHow to effectively review your gameplay.",
        encoding="utf-8"
    )

    # Create root level file
    (knowledge_dir / "core_theory.md").write_text(
        "# Core Theory\n\nFundamental game theory principles.",
        encoding="utf-8"
    )

    return knowledge_dir


@pytest.fixture
def sample_match_summaries():
    """Create sample MatchSummary objects for testing"""
    from src.coach.claude_coach import MatchSummary

    return [
        MatchSummary(
            champion="Jinx",
            role="BOTTOM",
            win=True,
            kills=8,
            deaths=3,
            assists=10,
            cs=220,
            cs_per_min=7.3,
            vision_score=25,
            damage_dealt=28000,
            game_duration_min=30,
            death_times=[450, 900, 1500]
        ),
        MatchSummary(
            champion="Caitlyn",
            role="BOTTOM",
            win=False,
            kills=5,
            deaths=6,
            assists=7,
            cs=180,
            cs_per_min=6.0,
            vision_score=18,
            damage_dealt=22000,
            game_duration_min=30,
            death_times=[300, 500, 800, 1100, 1400, 1700]
        ),
        MatchSummary(
            champion="Jinx",
            role="BOTTOM",
            win=False,
            kills=2,
            deaths=9,
            assists=3,
            cs=134,
            cs_per_min=4.8,
            vision_score=8,
            damage_dealt=12000,
            game_duration_min=28,
            death_times=[210, 380, 520, 680, 850, 1000, 1200, 1400, 1600]
        ),
    ]
